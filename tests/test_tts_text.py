"""PDF/LLM 줄바꿈이 발화 문장으로 합쳐지는 방식을 검증한다."""

import unittest

from voice.tts import TTSHelper


class TTSTextTests(unittest.TestCase):
    def sanitize(self, text):
        return TTSHelper._sanitize_text(None, text)

    def test_short_pdf_headings_get_pause(self):
        result = self.sanitize("아파트 입주자\n적용 범위 1\n공동주택 중 아파트 화재 시")
        self.assertEqual(result, "아파트 입주자. 적용 범위 1. 공동주택 중 아파트 화재 시")

    def test_long_wrapped_sentence_stays_together(self):
        result = self.sanitize("공동주택 구조와 환경적 특성에 맞춘 피난행동 요령을\n숙지할 필요")
        self.assertEqual(result, "공동주택 구조와 환경적 특성에 맞춘 피난행동 요령을 숙지할 필요")

    def test_page_break_is_not_spoken(self):
        result = self.sanitize("아파트 입주자\n--- PAGE BREAK ---\n적용 범위 1")
        self.assertNotIn("PAGE BREAK", result)
        self.assertIn("아파트 입주자. 적용 범위 1", result)

    def test_emergency_number_is_read_digit_by_digit(self):
        self.assertEqual(self.sanitize("119에 신고하고 119로 구조를 요청하세요."),
                         "일일구에 신고하고 일일구로 구조를 요청하세요.")
        self.assertEqual(self.sanitize("즉시119에 신고하세요. 119구급대"),
                         "즉시일일구에 신고하세요. 일일구구급대")
        self.assertEqual(self.sanitize("119"), "일일구")
        self.assertEqual(self.sanitize("신고 번호는 119."), "신고 번호는 일일구.")

    def test_other_numbers_are_preserved(self):
        text = "119명, 119개, 119초, 119미터, 1,119원, 1119, 119.5, A119, 제119조"
        self.assertEqual(self.sanitize(text), text)

    def test_non_korean_speech_is_not_rewritten(self):
        self.assertEqual(TTSHelper._sanitize_text(None, "Call 119", lang="en"), "Call 119")


if __name__ == "__main__":
    unittest.main()
