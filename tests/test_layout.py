"""구역별 대피로가 정확한 질문에만 주입되는지 확인한다."""

import unittest
from unittest.mock import patch

import config
from rag.layout import layout_for_question, layout_for_zone
from rag import provider


class LayoutTests(unittest.TestCase):
    def test_explicit_zone_question_gets_its_route(self):
        route = layout_for_question("B구역 대피경로가 어디야?")
        self.assertIn("B구역", route)
        self.assertIn("동쪽 비상구", route)
        self.assertNotIn("폐수처리장", route)

    def test_unknown_zone_is_not_assumed_to_be_a(self):
        self.assertEqual(layout_for_question("내부 대피경로 알려줘"), "")
        self.assertEqual(layout_for_zone("알 수 없는 구역"), "")

    @patch.object(config, "AI_PROVIDER", "gemini")
    @patch.object(config, "GEMINI_API_KEY", "test-key")
    @patch.object(provider, "_call_gemini", return_value="동쪽 비상구로 대피하십시오.")
    def test_allowed_route_is_sent_to_gemini(self, gemini):
        route = layout_for_question("B구역 대피경로")
        provider.generate_guidance(route, "B구역 대피경로", cloud_context=route)
        self.assertIn("동쪽 비상구", gemini.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
