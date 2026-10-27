import base64
import io
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from voice.gemini_tts import synthesize_to_file
from voice.tts import TTSHelper


def wav_bytes():
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b'\x01\x00' * 100)
    return out.getvalue()


class GeminiAudioTests(unittest.TestCase):
    def response(self, data, mime):
        response = Mock(ok=True)
        response.json.return_value = {'candidates': [{
            'finishReason': 'STOP', 'content': {'parts': [{'inlineData': {
                'mimeType': mime, 'data': base64.b64encode(data).decode()}}]}}]}
        return response

    def test_wav_response_is_not_wrapped_twice(self):
        data = wav_bytes()
        with tempfile.TemporaryDirectory() as folder, \
             patch('voice.gemini_tts.config.GEMINI_API_KEY', 'test-key'), \
             patch('voice.gemini_tts.config.GEMINI_TTS_MODEL', 'gemini-3.8-flash-lite-tts'), \
             patch('voice.gemini_tts.requests.post', return_value=self.response(data, 'audio/wav')) as post:
            target = Path(folder) / 'out.wav'
            synthesize_to_file('그대로 읽을 답변', target)
            self.assertEqual(target.read_bytes(), data)
            request = post.call_args.kwargs
            self.assertEqual(request['headers']['x-goog-api-key'], 'test-key')
            self.assertNotIn('test-key', post.call_args.args[0])
            self.assertEqual(request['json']['contents'][0]['parts'][0]['text'], '그대로 읽을 답변')
            self.assertEqual(request['json']['generationConfig']['speechConfig']['voiceConfig'], {'voice': 'Kore'})

    def test_raw_pcm_response_is_wrapped_as_wav(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch('voice.gemini_tts.config.GEMINI_API_KEY', 'test-key'), \
             patch('voice.gemini_tts.requests.post', return_value=self.response(b'\x01\x00' * 100, 'audio/L16;codec=pcm;rate=24000')):
            target = Path(folder) / 'out.wav'
            synthesize_to_file('시험', target)
            with wave.open(str(target)) as audio:
                self.assertEqual(audio.getframerate(), 24000)
                self.assertEqual(audio.getnframes(), 100)

    def test_quota_error_does_not_expose_body(self):
        with patch('voice.gemini_tts.config.GEMINI_API_KEY', 'test-key'), \
             patch('voice.gemini_tts.requests.post', return_value=Mock(ok=False, status_code=429)):
            with self.assertRaisesRegex(RuntimeError, '^Gemini TTS HTTP 429$'):
                synthesize_to_file('시험', 'unused.wav')

    def test_response_without_audio_is_rejected(self):
        response = Mock(ok=True)
        response.json.return_value = {'candidates': [{'content': {'parts': [{'text': 'no audio'}]}}]}
        with patch('voice.gemini_tts.config.GEMINI_API_KEY', 'test-key'), \
             patch('voice.gemini_tts.requests.post', return_value=response):
            with self.assertRaisesRegex(ValueError, 'audio missing'):
                synthesize_to_file('시험', 'unused.wav')


class GeminiRoutingTests(unittest.TestCase):
    def setUp(self):
        self.engine = Mock(initialized=True)
        def local(text, path, **kwargs):
            Path(path).write_bytes(wav_bytes())
            return True
        self.engine.speak_to_file.side_effect = local
        for patcher in (
            patch('voice.tts.PpasoEngine', return_value=self.engine),
            patch('voice.tts.config.TTS_ENGINE', 'PPASO'),
            patch('voice.tts.config.GEMINI_TTS_ENABLED', True),
            patch('voice.tts.config.GEMINI_API_KEY', 'test-key'),
            patch('voice.tts.pygame.mixer.get_init', return_value=False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.tts = TTSHelper()
        self.addCleanup(self.tts.close)
        self.played = []
        def play(path, generation, on_ready=None):
            if self.tts._valid(generation):
                if on_ready:
                    on_ready()
                self.played.append(path)
        player = patch.object(self.tts, '_play_file', side_effect=play)
        player.start()
        self.addCleanup(player.stop)

    def test_gemini_answer_prefers_cloud_while_local_and_fixed_do_not(self):
        def cloud(text, path):
            Path(path).write_bytes(wav_bytes())
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=cloud) as synth:
            for provider in ('gemini', 'zone', 'ollama', 'fixed', None):
                self.tts.speak('시험', provider=provider)
                self.assertTrue(self.tts.wait_until_idle(timeout=2))
            self.assertEqual(synth.call_count, 2)
            self.assertEqual(self.engine.speak_to_file.call_count, 3)
            self.assertEqual(len(self.played), 5)

    def test_pronunciation_changes_only_local_path_including_cloud_failure(self):
        source = 'CO2 소화기, 15m, E-STOP'
        def cloud(text, path):
            Path(path).write_bytes(wav_bytes())
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=cloud) as synth:
            self.tts.speak(source, provider='gemini')
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            cloud_text = synth.call_args.args[0]
            self.assertIn('CO2 소화기', cloud_text)
            self.assertIn('15 미터', cloud_text)
            self.assertNotIn('이산화탄소', cloud_text)
            self.engine.speak_to_file.assert_not_called()
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=RuntimeError('Gemini TTS HTTP 429')):
            self.tts.speak(source, provider='gemini')
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            local_text = self.engine.speak_to_file.call_args.args[0]
            self.assertIn('이산화탄소 소화기', local_text)
            self.assertIn('15 미터', local_text)
            self.assertIn('이 스톱', local_text)

    def test_event_replay_reuses_all_three_files_without_synthesis(self):
        def cloud(text, path):
            Path(path).write_bytes(wav_bytes())
        self.tts.begin_event_audio(1)
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=cloud) as synth:
            for part, provider in [('first', 'emergency'), ('zone', 'zone'), ('rules', 'gemini')]:
                self.tts.speak(part, provider=provider, cache_key=(1, part))
                self.assertTrue(self.tts.wait_until_idle(timeout=2))
            cached_paths = [self.tts._audio_cache[part][0] for part in ('first', 'zone', 'rules')]
            self.assertTrue(all(path.exists() for path in cached_paths))
            for _ in range(2):
                self.assertTrue(self.tts.replay_event_audio(1))
                self.assertTrue(self.tts.wait_until_idle(timeout=2))
            self.assertEqual(synth.call_count, 3)
            self.engine.speak_to_file.assert_not_called()
            self.assertEqual(self.played[-6:], cached_paths+cached_paths)
            self.tts.clear_event_audio(1)
            self.assertTrue(all(not path.exists() for path in cached_paths))

    def test_local_fallback_audio_is_also_cached(self):
        self.tts.begin_event_audio(1)
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=RuntimeError('Gemini TTS HTTP 429')) as synth:
            self.tts.speak('first', provider='emergency', cache_key=(1, 'first'))
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            self.assertEqual(self.tts._audio_cache['first'][1], 'PPASO')
            self.assertTrue(self.tts.replay_event_audio(1))
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            synth.assert_called_once()
            self.engine.speak_to_file.assert_called_once()

    def test_new_event_deletes_old_cache_and_old_event_cannot_replay(self):
        self.tts.begin_event_audio(1)
        self.tts.speak('local', provider='fixed', cache_key=(1, 'first'))
        self.assertTrue(self.tts.wait_until_idle(timeout=2))
        old_path = self.tts._audio_cache['first'][0]
        self.tts.stop()
        self.tts.begin_event_audio(2)
        self.assertFalse(old_path.exists())
        self.assertFalse(self.tts.replay_event_audio(1))
        self.assertFalse(self.tts.replay_event_audio(2))
        self.tts.clear_event_audio(1)
        self.assertEqual(self.tts._audio_group, 2)

    def test_cancelled_synthesis_cannot_enter_event_cache(self):
        self.tts.begin_event_audio(1)
        started, release = threading.Event(), threading.Event()
        def cloud(text, path):
            started.set()
            release.wait(2)
            Path(path).write_bytes(wav_bytes())
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=cloud):
            try:
                self.tts.speak('old', provider='emergency', cache_key=(1, 'first'))
                self.assertTrue(started.wait(1))
                self.tts.stop()
                self.tts.begin_event_audio(2)
            finally:
                release.set()
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            self.assertFalse(self.tts._audio_cache)
            self.assertFalse(self.tts.replay_event_audio(1))

    def test_stop_cancels_queued_replay_without_new_synthesis(self):
        self.tts.begin_event_audio(1)
        self.tts.speak('first', provider='fixed', cache_key=(1, 'first'))
        self.assertTrue(self.tts.wait_until_idle(timeout=2))
        self.played.clear()
        with self.tts._lock:
            self.assertTrue(self.tts.replay_event_audio(1))
            self.tts.stop()
        self.assertTrue(self.tts.wait_until_idle(timeout=2))
        self.assertFalse(self.played)

    def test_close_removes_event_cache_directory(self):
        directory = Path(self.tts._audio_cache_dir.name)
        self.tts.close()
        self.assertFalse(directory.exists())

    def test_first_emergency_uses_cloud_and_signals_ready_after_synthesis(self):
        ready = Mock()
        started, release = threading.Event(), threading.Event()
        def cloud(text, path):
            started.set()
            release.wait(2)
            Path(path).write_bytes(wav_bytes())
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=cloud) as synth:
            try:
                self.tts.speak('A구역에서 화재 위험이 감지되었습니다.', provider='emergency', on_ready=ready)
                self.assertTrue(started.wait(1))
                ready.assert_not_called()
            finally:
                release.set()
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            synth.assert_called_once()
            ready.assert_called_once()
            self.engine.speak_to_file.assert_not_called()

    def test_first_emergency_cloud_failure_keeps_ready_pending_until_local_audio(self):
        ready = Mock()
        def local(text, path, **kwargs):
            ready.assert_not_called()
            Path(path).write_bytes(wav_bytes())
            return True
        self.engine.speak_to_file.side_effect = local
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=RuntimeError('Gemini TTS HTTP 429')):
            self.tts.speak('첫 비상 안내', provider='emergency', on_ready=ready)
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            self.engine.speak_to_file.assert_called_once()
            ready.assert_called_once()

    def test_cancelled_first_emergency_does_not_signal_ready(self):
        ready = Mock()
        started, release = threading.Event(), threading.Event()
        def cloud(text, path):
            started.set()
            release.wait(2)
            Path(path).write_bytes(wav_bytes())
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=cloud):
            try:
                self.tts.speak('취소할 첫 안내', provider='emergency', on_ready=ready)
                self.assertTrue(started.wait(1))
                self.tts.stop()
            finally:
                release.set()
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            ready.assert_not_called()

    def test_manual_local_mode_keeps_first_emergency_local(self):
        self.tts.set_engine('PPASO')
        ready = Mock()
        with patch('voice.gemini_tts.synthesize_to_file') as synth:
            self.tts.speak('첫 안내', provider='emergency', on_ready=ready)
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            synth.assert_not_called()
            ready.assert_called_once()

    def test_ready_callback_requires_loaded_audio_and_current_generation(self):
        generation = self.tts._generation
        ready = Mock()
        with patch('voice.tts.pygame.mixer') as mixer:
            mixer.music.get_busy.return_value = False
            def audio_ready():
                mixer.music.load.assert_called_once()
                mixer.music.play.assert_not_called()
                ready()
            TTSHelper._play_file(self.tts, 'prepared.wav', generation, on_ready=audio_ready)
            ready.assert_called_once()
            ready.reset_mock()
            mixer.music.load.side_effect = RuntimeError('audio cannot load')
            with self.assertRaises(RuntimeError):
                TTSHelper._play_file(self.tts, 'failed.wav', generation, on_ready=ready)
            ready.assert_not_called()
            TTSHelper._play_file(self.tts, 'cancelled.wav', generation-1, on_ready=ready)
            ready.assert_not_called()

    def test_failure_falls_back_and_cooldown_skips_repeated_cloud_call(self):
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=RuntimeError('Gemini TTS HTTP 429')) as synth:
            for _ in range(2):
                self.tts.speak('시험', provider='gemini')
                self.assertTrue(self.tts.wait_until_idle(timeout=2))
            synth.assert_called_once()
            self.assertEqual(self.engine.speak_to_file.call_count, 2)
            self.assertEqual(self.tts.last_error, '')

    def test_manual_local_selection_overrides_gemini_until_auto(self):
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=lambda text, path: Path(path).write_bytes(wav_bytes())) as synth:
            self.tts.mode_command_response('/tts ppaso')
            self.tts.speak('시험', provider='gemini')
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            synth.assert_not_called()
            self.tts.mode_command_response('/tts auto')
            self.tts.speak('시험', provider='gemini')
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            synth.assert_called_once()

    def test_cancelled_cloud_audio_cannot_play_or_start_local_fallback(self):
        started, release = threading.Event(), threading.Event()
        def cloud(text, path):
            started.set()
            release.wait(2)
            Path(path).write_bytes(wav_bytes())
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=cloud):
            try:
                self.tts.speak('시험', provider='gemini')
                self.assertTrue(started.wait(1))
                self.tts.stop()
            finally:
                release.set()
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            self.assertEqual(self.played, [])
            self.engine.speak_to_file.assert_not_called()

    def test_disabled_cloud_stays_local_even_after_auto_command(self):
        with patch('voice.tts.config.GEMINI_TTS_ENABLED', False), \
             patch('voice.gemini_tts.synthesize_to_file') as synth:
            self.tts.mode_command_response('/tts auto')
            self.tts.speak('시험', provider='gemini')
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            synth.assert_not_called()
            self.engine.speak_to_file.assert_called_once()

    def test_explicit_gemini_command_enables_cloud_when_default_disabled(self):
        with patch('voice.tts.config.GEMINI_TTS_ENABLED', False), \
             patch('voice.gemini_tts.synthesize_to_file', side_effect=lambda text, path: Path(path).write_bytes(wav_bytes())) as synth:
            self.tts.mode_command_response('/tts auto')
            self.assertIn('Gemini TTS 우선', self.tts.mode_command_response('/tts gemini'))
            self.tts.speak('시험', provider='gemini')
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            synth.assert_called_once()
            self.engine.speak_to_file.assert_not_called()

    def test_missing_key_cannot_enable_cloud(self):
        self.tts.set_engine('PPASO')
        with patch('voice.tts.config.GEMINI_API_KEY', ''):
            self.assertIn('전환 실패', self.tts.mode_command_response('/tts gemini'))
        self.assertFalse(self.tts._prefer_gemini)

    def test_status_shows_sanitized_failure(self):
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=RuntimeError('Gemini TTS HTTP 429')):
            self.tts.speak('시험', provider='gemini')
            self.assertTrue(self.tts.wait_until_idle(timeout=2))
            self.assertIn('HTTP 429', self.tts.mode_command_response('/tts'))
            self.tts.mode_command_response('/tts gemini')
            self.assertNotIn('HTTP 429', self.tts.mode_command_response('/tts'))
