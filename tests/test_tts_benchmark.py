import unittest
from types import SimpleNamespace

from tools.benchmark_tts import korean_voice, summarize


class BenchmarkTests(unittest.TestCase):
    def test_linux_korean_language_bytes(self):
        voice = SimpleNamespace(id="korean", languages=[b"\x05ko"])
        self.assertIs(korean_voice([voice]), voice)

    def test_windows_korean_voice_id(self):
        voice = SimpleNamespace(id="TTS_MS_KO-KR_HEAMI", languages=[])
        self.assertIs(korean_voice([voice]), voice)

    def test_missing_voice_does_not_use_english(self):
        with self.assertRaises(RuntimeError):
            korean_voice([SimpleNamespace(id="english", languages=["en"])])

    def test_statistics_separate_sentences_and_failed_attempts(self):
        runs = [dict(text_index=0, status="ok", wall_s=1, cpu_s=2, audio_s=4, rtf=.25),
                dict(text_index=0, status="ok", wall_s=3, cpu_s=4, audio_s=4, rtf=.75),
                dict(text_index=0, status="failed"),
                dict(text_index=1, status="failed")]
        rows = summarize(runs, ["short", "long"])
        self.assertEqual(rows[0]["median_wall_s"], 2)
        self.assertEqual(rows[0]["successes"], 2)
        self.assertEqual(rows[0]["attempts"], 3)
        self.assertIsNone(rows[1]["median_rtf"])


if __name__ == "__main__":
    unittest.main()
