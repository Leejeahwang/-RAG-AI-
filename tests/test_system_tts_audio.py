import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from voice.tts import TTSHelper
from voice import tts_worker


class SystemAudioTests(unittest.TestCase):
    def test_linux_system_speech_uses_shared_player_and_removes_wav(self):
        with patch('voice.tts.config.TTS_ENGINE', 'PYTTSX3'), \
             patch('voice.tts.platform.system', return_value='Linux'), \
             patch('voice.tts.pygame.mixer.get_init', return_value=False):
            tts = TTSHelper()
            self.addCleanup(tts.close)
            paths = []
            def synth(text, lang, speed, generation, output_path=None):
                self.assertIsNotNone(output_path)
                Path(output_path).write_bytes(b'test audio')
                paths.append(output_path)
            def play(path, generation):
                self.assertTrue(path.exists())
                self.assertTrue(tts._valid(generation))
            with patch.object(tts, '_system_speech', side_effect=synth), \
                 patch.object(tts, '_play_file', side_effect=play) as player:
                tts.speak('한국어 시험')
                self.assertTrue(tts.wait_until_idle(timeout=2))
                player.assert_called_once()
                self.assertEqual(tts.last_error, '')
                self.assertTrue(all(not path.exists() for path in paths))

    def test_worker_exports_wav_without_direct_speech(self):
        engine = Mock()
        engine.getProperty.return_value = [SimpleNamespace(
            id='ko', name='Korean', languages=[b'\x05ko'])]
        with tempfile.TemporaryDirectory() as folder:
            output = str(Path(folder) / 'speech.wav')
            def save(text, path):
                with wave.open(path, 'wb') as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(22050)
                    audio.writeframes(b'\x01\x00' * 100)
            engine.save_to_file.side_effect = save
            with patch('voice.tts_worker.pyttsx3.init', return_value=engine), \
                 patch('voice.tts_worker.platform.system', return_value='Linux'):
                tts_worker.speak('시험', output_path=output)
            engine.say.assert_not_called()
            engine.setProperty.assert_any_call('voice', 'ko')
            self.assertTrue(Path(output).exists())

    def test_worker_rejects_missing_wav_even_if_driver_reports_completion(self):
        engine = Mock()
        engine.getProperty.return_value = [SimpleNamespace(
            id='ko', name='Korean', languages=['ko'])]
        with tempfile.TemporaryDirectory() as folder, \
             patch('voice.tts_worker.pyttsx3.init', return_value=engine), \
             patch('voice.tts_worker.platform.system', return_value='Linux'):
            with self.assertRaises(SystemExit) as error:
                tts_worker.speak('시험', output_path=str(Path(folder) / 'missing.wav'))
            self.assertEqual(error.exception.code, 1)
