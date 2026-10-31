import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from voice.tts import TTSHelper


class CachedVoiceUpgradeTests(unittest.TestCase):
    def setUp(self):
        engine = Mock(initialized=True)
        def local(text, path, **kwargs):
            Path(path).write_bytes(b'local speech')
            return True
        engine.speak_to_file.side_effect = local
        for patcher in (
            patch('voice.tts.config.TTS_ENGINE', 'PPASO'),
            patch('voice.tts.config.GEMINI_TTS_ENABLED', True),
            patch('voice.tts.config.GEMINI_API_KEY', 'test-key'),
            patch('voice.tts.config.AI_PROVIDER', 'auto'),
            patch('voice.tts.config.GEMINI_TTS_RETRY_COOLDOWN', 60),
            patch('voice.tts.PpasoEngine', return_value=engine),
            patch('voice.tts.pygame.mixer.get_init', return_value=False),
            # Exercise the actual retry step deterministically, without a
            # timer racing the test's mocked cloud responses.
            patch.object(TTSHelper, '_retry_cached_audio', return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.tts = TTSHelper()
        self.addCleanup(self.tts.close)
        self.played = []
        def play(path, generation, on_ready=None):
            if self.tts._valid(generation):
                self.played.append((Path(path), Path(path).read_bytes()))
                if on_ready:
                    on_ready()
                return True
            return False
        player = patch.object(self.tts, '_play_file', side_effect=play)
        player.start()
        self.addCleanup(player.stop)
        self.tts.begin_event_audio(1)

    def fallback(self, part='zone', provider='zone', text='CO2 소화기 위치'):
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=RuntimeError('Gemini TTS HTTP 429')):
            self.tts.speak(text, provider=provider, cache_key=(1, part))
            self.assertTrue(self.tts.wait_until_idle(2))
        return self.tts._audio_cache[part][0]

    @staticmethod
    def cloud(text, path):
        Path(path).write_bytes(b'cloud speech')

    def test_cooldown_then_upgrade_at_next_repeat_only(self):
        original = self.fallback()
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=self.cloud) as cloud:
            self.assertFalse(self.tts._retry_cached_audio_once())
            cloud.assert_not_called()
            self.tts._gemini_failure_until = 0
            self.assertTrue(self.tts._retry_cached_audio_once())
            self.assertEqual(cloud.call_args.args[0], 'CO2 소화기 위치')
            self.assertEqual(self.tts._audio_cache['zone'], (original, 'PPASO'))
            self.assertTrue(original.exists())
            self.assertTrue(self.tts.replay_event_audio(1))
            self.assertTrue(self.tts.wait_until_idle(2))
            self.assertEqual(self.played[-1][1], b'cloud speech')
            self.assertEqual(self.tts._audio_cache['zone'][1], 'GEMINI')
            self.assertFalse(original.exists())
            self.assertFalse(self.tts._retry_cached_audio_once())
            cloud.assert_called_once()

    def test_retry_failure_preserves_audio_and_enforces_cooldown(self):
        original = self.fallback()
        self.tts._gemini_failure_until = 0
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=RuntimeError('Gemini TTS HTTP 429')) as cloud:
            self.assertFalse(self.tts._retry_cached_audio_once())
            self.assertGreater(self.tts._gemini_failure_until, time.monotonic())
            self.assertFalse(self.tts._retry_cached_audio_once())
            cloud.assert_called_once()
        self.assertEqual(self.tts._audio_cache['zone'], (original, 'PPASO'))
        self.assertTrue(self.tts.replay_event_audio(1))
        self.assertTrue(self.tts.wait_until_idle(2))
        self.assertEqual(self.played[-1][1], b'local speech')

    def test_slow_cloud_upgrade_does_not_delay_replay_or_delete_playing_file(self):
        original = self.fallback()
        self.tts._gemini_failure_until = 0
        started, release = threading.Event(), threading.Event()
        def slow(text, path):
            started.set()
            release.wait(3)
            self.cloud(text, path)
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=slow):
            thread = threading.Thread(target=self.tts._retry_cached_audio_once)
            thread.start()
            try:
                self.assertTrue(started.wait(1))
                self.assertTrue(self.tts.replay_event_audio(1))
                self.assertTrue(self.tts.wait_until_idle(1))
                self.assertEqual(self.played[-1][1], b'local speech')
                self.assertTrue(original.exists())
            finally:
                release.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())

    def test_inflight_upgrade_cannot_enter_new_event_or_survive_close(self):
        for action in ('new', 'local', 'close'):
            with self.subTest(action=action):
                self.tts.set_engine('GEMINI')
                self.tts.begin_event_audio(1)
                self.fallback()
                self.tts._gemini_failure_until = self.tts._cache_retry_after = 0
                paths = []
                def stale(text, path):
                    paths.append(path)
                    self.cloud(text, path)
                    if action == 'new':
                        self.tts.stop()
                        self.tts.begin_event_audio(2)
                    elif action == 'close':
                        self.tts.close()
                    else:
                        self.tts.set_engine('PPASO')
                with patch('voice.gemini_tts.synthesize_to_file', side_effect=stale):
                    self.assertFalse(self.tts._retry_cached_audio_once())
                self.assertFalse(self.tts._cache_upgrades)
                self.assertTrue(all(not path.exists() for path in paths))

    def test_local_modes_never_schedule_cloud_upgrade(self):
        self.fallback()
        self.tts._gemini_failure_until = 0
        with patch('voice.gemini_tts.synthesize_to_file') as cloud:
            with patch('voice.tts.config.AI_PROVIDER', 'local'):
                self.assertFalse(self.tts._retry_cached_audio_once())
            self.tts.set_engine('PPASO')
            self.assertFalse(self.tts._retry_cached_audio_once())
            cloud.assert_not_called()

    def test_fixed_local_speech_has_no_upgrade_metadata(self):
        self.fallback(provider='fixed')
        self.assertFalse(self.tts._cache_sources)

    def test_successful_upgrade_is_rate_limited_before_next_part(self):
        self.fallback(part='first', provider='emergency')
        self.fallback(part='zone')
        self.tts._gemini_failure_until = 0
        with patch('voice.gemini_tts.synthesize_to_file', side_effect=self.cloud) as cloud:
            self.assertTrue(self.tts._retry_cached_audio_once())
            self.assertFalse(self.tts._retry_cached_audio_once())
            cloud.assert_called_once()
        prepared = self.tts._cache_upgrades['first'][0]
        self.tts.clear_event_audio(1)
        self.assertFalse(prepared.exists())
        self.assertFalse(self.tts._cache_sources)


if __name__ == '__main__':
    unittest.main()
