import tempfile
import threading
import unittest
import wave
from array import array
from pathlib import Path
from unittest.mock import Mock, patch

from voice.tts import TTSHelper


class SpeechRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.config = patch('voice.tts.config.TTS_ENGINE', 'PYTTSX3')
        self.config.start()
        self.addCleanup(self.config.stop)
        self.mixer_patch = patch('voice.tts.pygame.mixer')
        self.mixer = self.mixer_patch.start()
        self.addCleanup(self.mixer_patch.stop)
        self.tts = TTSHelper()
        self.addCleanup(self.tts.close)

    def test_failed_play_does_not_stop_siren_and_retries_same_file(self):
        self.mixer.music.play.side_effect = [RuntimeError('device lost'), None]
        self.mixer.music.get_busy.side_effect = [True, False]
        ready = Mock()
        def started():
            self.assertEqual(self.mixer.music.play.call_count, 2)
            ready()
        self.assertTrue(self.tts._play_with_retry('speech.wav', 0, started))
        ready.assert_called_once()
        self.mixer.quit.assert_not_called()
        self.assertEqual(self.mixer.music.load.call_count, 2)

    def test_play_returning_without_start_is_failure(self):
        self.mixer.music.get_busy.return_value = False
        ready = Mock()
        with self.assertRaisesRegex(RuntimeError, 'did not start'):
            self.tts._play_with_retry('speech.wav', 0, ready)
        ready.assert_not_called()
        self.assertEqual(self.mixer.music.play.call_count, 2)

    def test_cancellation_during_failed_play_does_not_retry(self):
        def cancel():
            self.tts.stop()
            raise RuntimeError('cancelled')
        self.mixer.music.play.side_effect = cancel
        self.assertFalse(self.tts._play_with_retry('speech.wav', 0, Mock()))
        self.assertEqual(self.mixer.music.play.call_count, 1)

    def test_device_failure_preserves_synthesized_event_for_later_repeat(self):
        self.tts.begin_event_audio(1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'speech.wav'
            path.write_bytes(b'prepared audio')
            with patch.object(self.tts, '_play_file', side_effect=RuntimeError('device lost')):
                with self.assertRaises(RuntimeError):
                    self.tts._play_and_cache(path, 0, None, (1, 'first'), 'PPASO')
            cached, engine = self.tts._audio_cache['first']
            self.assertEqual(cached.read_bytes(), b'prepared audio')
            self.assertEqual(engine, 'PPASO')
            with patch.object(self.tts, '_play_file') as play:
                self.assertTrue(self.tts.replay_event_audio(1))
                self.assertTrue(self.tts.wait_until_idle(2))
                play.assert_called_once_with(cached, 0)

    def test_pause_detection_preserves_voiced_words_and_decimal_notation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'speech.wav'
            # Voiced 400 ms, quiet 320 ms, voiced 400 ms. Only the gap
            # is an eligible boundary; text punctuation is not guessed.
            with wave.open(str(path), 'wb') as audio:
                audio.setparams((1, 2, 1000, 0, 'NONE', ''))
                audio.writeframes(array('h', [3000] * 400 + [0] * 320 + [3000] * 400).tobytes())
            points = self.tts._speech_pauses(path)
            self.assertTrue(points)
            self.assertEqual(len(points), 1)
            self.assertAlmostEqual(points[0][0], .44)
            self.assertAlmostEqual(points[0][1], .68)

    def test_new_fire_pauses_at_gap_and_cancels_old_clip(self):
        playing = threading.Event()
        self.mixer.music.play.side_effect = playing.set
        self.mixer.music.get_busy.return_value = True
        self.mixer.music.get_pos.return_value = 100
        with patch.object(self.tts, '_speech_pauses', return_value=[(.6, .8)]):
            thread = threading.Thread(target=self.tts._play_file, args=('speech.wav', 0))
            thread.start()
            try:
                self.assertTrue(playing.wait(1))
                self.tts.request_boundary()
                self.assertFalse(self.tts._yield_ready.wait(.08))
                self.mixer.music.get_pos.return_value = 650
                self.assertTrue(self.tts._yield_ready.wait(1))
                self.mixer.music.pause.assert_called_once()
                self.tts.stop()
                thread.join(1)
                self.assertFalse(thread.is_alive())
                self.mixer.music.unpause.assert_not_called()
            finally:
                self.tts.stop()
                thread.join(1)

    def test_withdrawn_update_resumes_paused_audio(self):
        playing = threading.Event()
        scanned = threading.Event()
        self.mixer.music.play.side_effect = playing.set
        self.mixer.music.get_busy.return_value = True
        self.mixer.music.get_pos.return_value = 650
        def pauses(path):
            scanned.set()
            return [(.7, .9)]
        with patch.object(self.tts, '_speech_pauses', side_effect=pauses):
            thread = threading.Thread(target=self.tts._play_file, args=('speech.wav', 0))
            thread.start()
            try:
                self.assertTrue(playing.wait(1))
                self.tts.request_boundary()
                self.assertTrue(scanned.wait(1))
                self.mixer.music.get_pos.return_value = 750
                self.assertTrue(self.tts._yield_ready.wait(1))
                self.tts.cancel_boundary()
                self.mixer.music.get_busy.return_value = False
                thread.join(1)
                self.assertFalse(thread.is_alive())
                self.mixer.music.unpause.assert_called_once()
            finally:
                self.tts.stop()
                thread.join(1)

    def test_gap_passed_during_scan_does_not_cut_next_word(self):
        playing, scanned = threading.Event(), threading.Event()
        self.mixer.music.play.side_effect = playing.set
        self.mixer.music.get_busy.return_value = True
        self.mixer.music.get_pos.return_value = 100
        def scan(path):
            self.mixer.music.get_pos.return_value = 900
            scanned.set()
            return [(.2, .5)]
        with patch.object(self.tts, '_speech_pauses', side_effect=scan):
            thread = threading.Thread(target=self.tts._play_file, args=('speech.wav', 0))
            thread.start()
            try:
                self.assertTrue(playing.wait(1))
                self.tts.request_boundary()
                self.assertTrue(scanned.wait(1))
                self.assertFalse(self.tts._yield_ready.wait(.08))
                self.mixer.music.pause.assert_not_called()
                # No remaining gaps: yield at EOF before another old clip.
                self.mixer.music.get_busy.return_value = False
                self.assertTrue(self.tts._yield_ready.wait(1))
            finally:
                self.tts.stop()
                thread.join(1)
                self.assertFalse(thread.is_alive())


if __name__ == '__main__':
    unittest.main()
