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
        def play(path, generation):
            if self.tts._valid(generation):
                self.played.append(path)
        player = patch.object(self.tts, '_play_file', side_effect=play)
        player.start()
        self.addCleanup(player.stop)

    def test_gemini_answer_prefers_cloud_while_local_and_fixed_do_not(self):
        def cloud(text, path):
            Path(path).write_bytes(wav_bytes())
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=cloud) as synth:
            for provider in ('gemini', 'ollama', 'fixed', None):
                self.tts.speak('시험', provider=provider)
                self.assertTrue(self.tts.wait_until_idle(timeout=2))
            synth.assert_called_once()
            self.assertEqual(self.engine.speak_to_file.call_count, 3)
            self.assertEqual(len(self.played), 4)

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
