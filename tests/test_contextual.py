import json
import unittest
from unittest.mock import Mock, patch

import config
from rag import provider
from rag.contextual import contextual_request, render_contextual


def response(items):
    return json.dumps({'items': items}, ensure_ascii=False)


class ContextualTests(unittest.TestCase):
    def test_general_instruction_can_be_rephrased(self):
        text = render_contextual(response([{'instruction_id': 1, 'guidance': '즉시 작업을 멈추세요.'}]),
            ['즉시 작업을 중단하십시오.'], {'fire_zone': 'A', 'local_zone': 'B'})
        self.assertIn('즉시 작업을 멈추세요.', text)
        self.assertIn('화재 구역은 A구역', text)
        self.assertIn('안내 구역은 B구역', text)

    def test_critical_facts_and_prohibitions_restore_source(self):
        for source, invented in [
            ('북쪽 로비 방향으로 15m 직진하십시오.', '남쪽으로 30m 가세요.'),
            ('물을 사용하지 마십시오.', '물을 사용하세요.'),
            ('전기 화재인 경우 전원을 차단하십시오.', '전기 화재입니다. 전원을 차단하세요.'),
            ('B구역 소화기 위치: 동쪽 비상구입니다.', 'A구역 서쪽에 소화기가 있습니다.'),
        ]:
            with self.subTest(source=source):
                self.assertEqual(render_contextual(response([{'instruction_id': 1, 'guidance': invented}]), [source], {}), source)

    def test_unobserved_safety_or_route_claim_is_replaced(self):
        source = '작업을 중단하십시오.'
        for invented in ('출구가 안전합니다.', '계단이 막혀 있습니다.', '연기가 퍼졌습니다.', '불을 향해 걸어가세요.'):
            self.assertEqual(render_contextual(response([{'instruction_id': 1, 'guidance': invented}]), [source], {}), source)

    def test_ids_json_and_empty_output_are_validated(self):
        for value in ('broken', '{}', response([]), response([{'instruction_id': True, 'guidance': '중단하세요.'}]),
                      response([{'instruction_id': 2, 'guidance': '중단하세요.'}])):
            with self.subTest(value=value), self.assertRaises(ValueError):
                render_contextual(value, ['작업을 중단하십시오.'], {})

    def test_origin_profile_obeys_layout_privacy_setting(self):
        with patch.object(config, 'GEMINI_SEND_LAYOUT', True):
            system, user, schema, passages, facts = contextual_request('작업을 중단하십시오.', '화재',
                {'fire_zone': 'A', 'local_zone': 'B'}, True)
        self.assertIn('화학물질', user)
        self.assertIn('실제 발화 원인', system)
        self.assertIn('일반 대피·재진입 금지', system)
        self.assertIn('진압 수칙을 나열하지', system)
        self.assertEqual(facts, {'fire_zone': 'A', 'local_zone': 'B'})
        with patch.object(config, 'GEMINI_SEND_LAYOUT', False):
            user = contextual_request('작업을 중단하십시오.', '화재', {'fire_zone': 'A'}, True)[1]
        self.assertEqual(json.loads(user)['origin_zone_reference'], '')

    @patch.object(config, 'AI_PROVIDER', 'gemini')
    @patch.object(config, 'GEMINI_API_KEY', 'test-key')
    def test_contextual_routing_and_extractive_rollback(self):
        with patch.object(config, 'GEMINI_GUIDANCE_STYLE', 'contextual'), \
             patch.object(provider, '_gemini_request', return_value=response([
                 {'instruction_id': 1, 'guidance': '작업을 멈추세요.'}])) as request, \
             patch.object(provider, '_local') as local:
            result = provider.generate_guidance('작업을 중단하십시오.', '화재', emergency=True,
                situation={'fire_zone': 'A', 'local_zone': 'B'})
            self.assertEqual(result.provider, 'gemini')
            self.assertIn('작업을 멈추세요.', result.text)
            self.assertEqual(request.call_args.args[0]['generationConfig']['responseMimeType'], 'application/json')
            local.assert_not_called()
        with patch.object(config, 'GEMINI_GUIDANCE_STYLE', 'extractive'), \
             patch.object(provider, '_call_gemini', return_value='작업을 중단하십시오.') as original:
            result = provider.generate_guidance('작업을 중단하십시오.', '화재', emergency=True)
            self.assertEqual(result.text, '작업을 중단하십시오.')
            original.assert_called_once_with('작업을 중단하십시오.', '화재', require_quotes=True)

    @patch.object(config, 'AI_PROVIDER', 'gemini')
    @patch.object(config, 'GEMINI_API_KEY', 'test-key')
    @patch.object(config, 'GEMINI_GUIDANCE_STYLE', 'contextual')
    def test_invalid_contextual_answer_keeps_local_fallback(self):
        with patch.object(provider, '_gemini_request', return_value='broken'), \
             patch.object(provider, '_local', return_value='작업을 중단하십시오.'):
            result = provider.generate_guidance('작업을 중단하십시오.', '화재', emergency=True)
        self.assertEqual(result.provider, 'ollama')


if __name__ == '__main__':
    unittest.main()
