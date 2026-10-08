"""API 연결 여부와 무관하게 공급자 전환을 검증한다."""

import unittest
from unittest.mock import patch

import requests

import config
from rag import provider


class ProviderTests(unittest.TestCase):
    def setUp(self):
        provider._failure_until = 0.0

    def test_grounding_accepts_factory_markdown_and_quote_differences(self):
        source = "* **상황 A: 전기 화재**\n  - '메인 전원(차단기)'을 내린 후, `CO2` 소화기를 사용합니다."
        answer = '상황 A: 전기 화재\n1. 메인 전원(차단기)을 내린 후, CO2 소화기를 사용합니다.'
        self.assertTrue(provider._is_grounded(answer, source))

    def test_grounding_preserves_route_numbers_and_prohibitions(self):
        source = "B동 2번 계단으로 대피하십시오.\n물을 사용하지 마십시오.\n2.5미터 거리를 유지하십시오."
        for answer in ("B동 3번 계단으로 대피하십시오.", "물을 사용하십시오.", "5미터 거리를 유지하십시오."):
            with self.subTest(answer=answer):
                self.assertFalse(provider._is_grounded(answer, source))
        self.assertTrue(provider._is_grounded("2.5미터 거리를 유지하십시오.", source))

    def test_grounding_rejects_partial_word_and_empty_markup(self):
        self.assertFalse(provider._is_grounded("물을 사용", "물을 사용하지 마십시오."))
        self.assertFalse(provider._is_grounded("**", "매뉴얼"))

    @patch.object(config, "AI_PROVIDER", "auto")
    @patch.object(config, "GEMINI_API_KEY", "test-key")
    @patch.object(provider, "_local")
    @patch("rag.provider.requests.post")
    def test_online_answer_uses_gemini(self, post, local):
        post.return_value.json.return_value = {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "안전한 곳으로 대피하십시오."}]}}]
        }
        result = provider.generate_guidance("안전한 곳으로 대피하십시오.", "어떻게 해야 하나요?")
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.text, "안전한 곳으로 대피하십시오.")
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "test-key")
        local.assert_not_called()

    @patch.object(config, "AI_PROVIDER", "auto")
    @patch.object(config, "GEMINI_API_KEY", "")
    @patch.object(provider, "_local", return_value="로컬 답변")
    @patch("rag.provider.requests.post")
    def test_missing_key_uses_local_without_network(self, post, local):
        result = provider.generate_guidance("매뉴얼", "질문")
        self.assertEqual(result.provider, "ollama")
        self.assertEqual(result.fallback_reason, "Gemini API 키 없음")
        post.assert_not_called()
        local.assert_called_once()

    @patch.object(config, "AI_PROVIDER", "auto")
    @patch.object(config, "GEMINI_API_KEY", "test-key")
    @patch.object(provider, "_local", return_value="로컬 답변")
    @patch("rag.provider.requests.post", side_effect=requests.Timeout("timeout"))
    def test_timeout_falls_back_and_opens_cooldown(self, post, local):
        first = provider.generate_guidance("매뉴얼", "질문")
        second = provider.generate_guidance("매뉴얼", "질문")
        self.assertEqual(first.provider, "ollama")
        self.assertEqual(second.fallback_reason, "Gemini 재시도 대기 중")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(local.call_count, 2)

    @patch.object(config, "AI_PROVIDER", "auto")
    @patch.object(config, "GEMINI_API_KEY", "test-key")
    @patch.object(provider, "_local", return_value="로컬 답변")
    @patch("rag.provider.requests.post")
    def test_ungrounded_cloud_answer_is_rejected(self, post, local):
        post.return_value.json.return_value = {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "없는 서쪽 출구로 가십시오."}]}}]
        }
        with self.assertLogs(provider._LOG, level="WARNING") as logs:
            result = provider.generate_guidance("동쪽 계단으로 대피하십시오.", "어디로 가나요?", emergency=True)
        self.assertEqual(result.provider, "fixed")
        self.assertEqual(result.text, provider.EMERGENCY_GUIDANCE)
        self.assertIn("매뉴얼 원문과 일치하지 않습니다", logs.output[0])

    @patch.object(config, "AI_PROVIDER", "auto")
    @patch.object(config, "GEMINI_API_KEY", "test-key")
    @patch.object(provider, "_local")
    @patch("rag.provider.requests.post")
    def test_normal_question_accepts_paraphrase_without_fallback(self, post, local):
        post.return_value.json.return_value = {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "안전한 동쪽 계단을 이용해 대피하세요."}]}}]
        }
        result = provider.generate_guidance("동쪽 계단으로 대피하십시오.", "어디로 가나요?")
        self.assertEqual(result.provider, "gemini")
        local.assert_not_called()
        prompt = post.call_args.kwargs["json"]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("요약", prompt)

    @patch.object(config, "AI_PROVIDER", "auto")
    @patch.object(config, "GEMINI_API_KEY", "test-key")
    @patch.object(provider, "_local", return_value="로컬 답변")
    @patch("rag.provider.requests.post")
    def test_empty_text_still_falls_back_in_normal_mode(self, post, local):
        post.return_value.json.return_value = {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": " "}]}}]
        }
        with self.assertLogs(provider._LOG, level="WARNING") as logs:
            result = provider.generate_guidance("매뉴얼", "질문")
        self.assertEqual(result.provider, "ollama")
        self.assertIn("답변이 비어 있습니다", logs.output[0])

    @patch.object(config, "AI_PROVIDER", "auto")
    @patch.object(config, "GEMINI_API_KEY", "test-key")
    @patch.object(provider, "_local", return_value="로컬 답변")
    @patch("rag.provider.requests.post")
    def test_truncated_answer_logs_finish_reason_and_falls_back(self, post, local):
        post.return_value.json.return_value = {
            "candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "일부 답변"}]}}]
        }
        with self.assertLogs(provider._LOG, level="WARNING") as logs:
            result = provider.generate_guidance("매뉴얼", "질문")
        self.assertEqual(result.provider, "ollama")
        self.assertIn("MAX_TOKENS", logs.output[0])

    @patch.object(config, "AI_PROVIDER", "auto")
    @patch.object(config, "GEMINI_API_KEY", "test-key")
    @patch.object(provider, "_local", return_value="로컬 답변")
    @patch("rag.provider.requests.post")
    def test_rate_limit_falls_back(self, post, local):
        post.return_value.raise_for_status.side_effect = requests.HTTPError("429")
        result = provider.generate_guidance("매뉴얼", "질문")
        self.assertEqual(result.provider, "ollama")
        self.assertEqual(result.fallback_reason, "HTTPError")

    @patch.object(config, "AI_PROVIDER", "auto")
    @patch.object(config, "GEMINI_API_KEY", "test-key")
    @patch.object(provider, "_local", return_value="로컬 답변")
    @patch("rag.provider.requests.post")
    def test_empty_cloud_context_is_not_sent(self, post, local):
        result = provider.generate_guidance("로컬 전용 평면도", "질문", cloud_context="")
        self.assertEqual(result.provider, "ollama")
        post.assert_not_called()

    @patch.object(config, "AI_PROVIDER", "local")
    @patch.object(provider, "_local", return_value="없는 출구로 가세요")
    def test_ungrounded_emergency_local_answer_uses_fixed_guidance(self, local):
        result = provider.generate_guidance("매뉴얼 원문", "질문", emergency=True)
        self.assertEqual(result.provider, "fixed")
        self.assertEqual(result.text, provider.EMERGENCY_GUIDANCE)

    @patch.object(config, "AI_PROVIDER", "local")
    @patch.object(provider, "_local", side_effect=RuntimeError("offline"))
    def test_emergency_has_fixed_fallback(self, local):
        result = provider.generate_guidance("매뉴얼", "질문", emergency=True)
        self.assertEqual(result.provider, "fixed")
        self.assertEqual(result.text, provider.EMERGENCY_GUIDANCE)

    @patch.object(config, "AI_PROVIDER", "auto")
    @patch.object(config, "GEMINI_API_KEY", "test-key")
    @patch.object(provider, "_local", return_value="로컬 답변")
    @patch.object(provider, "_call_gemini", return_value="매뉴얼 문장")
    def test_runtime_mode_switch_changes_next_request(self, gemini, local):
        provider.set_ai_mode("local")
        first = provider.generate_guidance("매뉴얼 문장", "질문")
        self.assertEqual(first.provider, "ollama")
        gemini.assert_not_called()

        provider.set_ai_mode("api")
        second = provider.generate_guidance("매뉴얼 문장", "질문")
        self.assertEqual(provider.get_ai_mode(), "gemini")
        self.assertEqual(second.provider, "gemini")
        gemini.assert_called_once()

    @patch.object(config, "AI_PROVIDER", "auto")
    def test_cli_mode_command(self):
        self.assertIsNone(provider.mode_command_response("화재 시 대피 방법"))
        self.assertIn("로컬 고정", provider.mode_command_response("/ai local"))
        self.assertEqual(provider.get_ai_mode(), "local")
        self.assertIn("사용법", provider.mode_command_response("/ai wrong"))
        self.assertEqual(provider.get_ai_mode(), "local")


if __name__ == "__main__":
    unittest.main()
