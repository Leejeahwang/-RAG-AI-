import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from voice.tts import TTSHelper


class SpeechCancellationTests(unittest.TestCase):
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
