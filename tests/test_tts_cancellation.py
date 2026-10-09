import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from voice.tts import TTSHelper


class SpeechCancellationTests(unittest.TestCase):
    def test_switch_during_synthesis_discards_old_audio_and_uses_system_engine(self):
        started, release = threading.Event(), threading.Event()
        class Engine:
            initialized = True
            def speak_to_file(self, text, path, **kwargs):
                started.set()
                release.wait(2)
                Path(path).write_text(text, encoding='utf-8')
                return True
        with patch('voice.tts.PpasoEngine', return_value=Engine()), \
             patch('voice.tts.config.TTS_ENGINE', 'PPASO'), \
             patch('voice.tts.pygame.mixer.get_init', return_value=False):
            tts = TTSHelper()
            self.addCleanup(tts.close)
            played = []
            def play(path, generation):
                if tts._valid(generation):
                    played.append(str(path))
            with patch.object(tts, '_play_file', side_effect=play), \
                 patch.object(tts, '_system_speech') as system:
                try:
                    tts.speak('old answer')
                    self.assertTrue(started.wait(1))
                    self.assertIn('PYTTSX3', tts.mode_command_response('/tts pyttsx3'))
                    tts.speak('new answer')
                finally:
                    release.set()
                self.assertTrue(tts.wait_until_idle(timeout=2))
                self.assertEqual(played, [])
                system.assert_called_once()
                self.assertEqual(system.call_args.args[0], 'new answer')
                self.assertTrue(tts.set_engine('PPASO'))

    def test_failed_switch_keeps_current_engine_and_pending_generation(self):
        with patch('voice.tts.config.TTS_ENGINE', 'PYTTSX3'), \
             patch('voice.tts.PpasoEngine') as engine, \
             patch('voice.tts.pygame.mixer.get_init', return_value=False):
            engine.return_value.initialized = False
            tts = TTSHelper()
            self.addCleanup(tts.close)
            generation = tts._generation
            self.assertIsNone(tts.mode_command_response('normal question'))
            self.assertIn('사용법', tts.mode_command_response('/tts invalid'))
            self.assertIn('전환 실패', tts.mode_command_response('/tts ppaso'))
            self.assertEqual(tts.engine_type, 'PYTTSX3')
            self.assertEqual(tts._generation, generation)

    def test_synthesis_finishing_after_stop_cannot_play_old_answer(self):
        started, release = threading.Event(), threading.Event()
        played=[]
        class Engine:
            initialized=True
            def speak_to_file(self,text,path,**kwargs):
                if text=='old answer':
                    started.set()
                    release.wait(2)
                Path(path).write_text(text,encoding='utf-8')
                return True
        with patch('voice.tts.PpasoEngine',return_value=Engine()), \
             patch('voice.tts.config.TTS_ENGINE','PPASO'), \
             patch('voice.tts.pygame.mixer.get_init',return_value=False):
            tts=TTSHelper()
            try:
                def play(path,generation):
                    if tts._valid(generation):
                        played.append(Path(path).read_text(encoding='utf-8'))
                with patch.object(tts,'_play_file',side_effect=play):
                    tts.speak('old answer')
                    self.assertTrue(started.wait(1))
                    tts.stop()
                    tts.speak('emergency')
                    release.set()
                    self.assertTrue(tts.wait_until_idle(timeout=2))
                    self.assertEqual(played,['emergency'])
            finally:
                release.set()
                tts.close()
            self.assertFalse(tts._worker_thread.is_alive())


if __name__=='__main__':
    unittest.main()
