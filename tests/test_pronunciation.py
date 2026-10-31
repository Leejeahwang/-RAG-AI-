"""Quantity-preserving speech normalization and engine boundary regressions."""
import unittest
from unittest.mock import Mock

from voice.pronunciation import local_pronunciation, preserve_spoken_notation
from voice.ppaso_wrapper import PpasoEngine
from voice.tts import TTSHelper


class PronunciationTests(unittest.TestCase):
    def test_formula_spellings_and_embedded_identifiers(self):
        self.assertEqual(local_pronunciation('CO2·CO₂ 소화기, N2, O₂, H2O'),
                         '이산화탄소·이산화탄소 소화기, 질소, 산소, 물')
        for text in ('NaHCO3', 'CO20', 'MYCO2', 'H2O2', 'O2_test'):
            self.assertEqual(local_pronunciation(text), text)

    def test_reviewed_acronyms_not_larger_words(self):
        self.assertEqual(local_pronunciation('ABC, BC, CPR, GPS, AED, AI, E-STOP, E/V홀'),
                         '에이비씨, 비씨, 씨피알, 지피에스, 에이이디, 에이아이, 이 스톱, 엘리베이터홀')
        self.assertEqual(local_pronunciation('A3 KFSC101 ABCD PAID'), 'A3 KFSC101 ABCD PAID')

    def test_units_ranges_temperature_and_sign_survive_sanitizer(self):
        samples = {
            '15m 직진': '15 미터 직진',
            '1.5 m 이하': '1.5 미터 이하',
            '75℃': '섭씨 75 도', '80%': '80 퍼센트',
            '섭씨 75℃': '섭씨 75 도',
            '-5도': '마이너스 5도', '-5℃': '섭씨 마이너스 5 도',
            '10~15m': '10 미터에서 15 미터',
            '-5~-1℃': '섭씨 마이너스 5 도에서 섭씨 마이너스 1 도',
            '3~5분': '3분에서 5분',
            '33㎡': '33 제곱미터', '2㎥': '2 세제곱미터',
            '9.8kg': '9.8 킬로그램', '5cm': '5 센티미터',
            '30km/h': '시속 30 킬로미터', '0.5m/s': '초속 0.5 미터',
            '100mL': '100 밀리리터',
        }
        for source, expected in samples.items():
            with self.subTest(source=source):
                self.assertEqual(TTSHelper._sanitize_text(None, source), expected)

    def test_decimal_and_grouped_numbers_keep_value(self):
        for source, expected in [('1.05m', '일 점 영오 미터'), ('9.8kg', '구 점 팔 킬로그램'),
                                 ('1,500m', '천오백 미터'), ('0.5', '영 점 오'), ('1.05.', '일 점 영오.')]:
            self.assertEqual(local_pronunciation(source), expected)
        for source in ('v1.5', '192.168.0.1', 'A1.5', 'KFSC101', 'A10-15m', '3kg/cm2'):
            self.assertEqual(local_pronunciation(source), source)

    def test_non_korean_and_gemini_terms_unchanged(self):
        text = 'CO2 15m 75℃ E/V E-STOP'
        self.assertEqual(local_pronunciation(text, 'en'), text)
        self.assertEqual(preserve_spoken_notation(text, 'en'), text)
        common = TTSHelper._sanitize_text(None, 'CO2 소화기 15m')
        self.assertIn('CO2', common)
        self.assertNotIn('이산화탄소', common)

    def test_zone_lists_and_idempotence(self):
        self.assertEqual(preserve_spoken_notation('A·B·C구역'), 'A구역과 B구역과 C구역')
        text = local_pronunciation('CO₂, 10~15m, -5℃, 1.5kg, A·C구역')
        self.assertEqual(local_pronunciation(text), text)

    def test_direct_ppaso_calls_are_corrected_before_synthesis(self):
        engine = object.__new__(PpasoEngine)
        engine.initialized, engine.sample_rate = True, 22050
        engine.tts, engine.sf = Mock(), Mock()
        engine.tts.synthesize.return_value = [0.0, 0.0]
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(engine.speak_to_file('CO2 소화기, 15m', str(Path(folder)/'out.wav')))
        engine.tts.synthesize.assert_called_once_with('이산화탄소 소화기, 15 미터', chunked=True)


if __name__ == '__main__':
    unittest.main()
