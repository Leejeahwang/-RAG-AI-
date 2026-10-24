import unittest

from rag.context import build_manual_context, additional_fire_context, without_repeated_guidance, instruction_passages


class ContextTests(unittest.TestCase):
    def test_action_selection_excludes_titles_and_preserves_fire_conditions(self):
        context = ('산업용 공장 화재 대응 매뉴얼\n1. 화재 종류별 수칙\n'
                   '* **상황 A: 전기 화재 발생 시**\n- 물을 사용하지 마십시오.\n'
                   '* **상황 B: 화학물질 화재 발생 시**\n- 해당 구역을 이탈하세요.')
        passages = instruction_passages(context)
        self.assertEqual(len(passages), 2)
        self.assertIn('상황 A', passages[0])
        self.assertIn('물을 사용하지', passages[0])
        self.assertIn('상황 B', passages[1])
        self.assertNotIn('매뉴얼', '\n'.join(passages))
    def test_additional_context_excludes_zone_files_but_keeps_conditions(self):
        result = additional_fire_context([
            {'source': 'zone_B_layout.txt', 'page_content': 'B구역 출구'},
            {'source': 'factory.txt', 'page_content': '### 전기 화재인 경우\n물을 사용하지 마십시오.'},
            {'source': 'gas_poisoning.txt', 'page_content': '창문을 열고 환기를 시키세요.'},
        ])
        self.assertNotIn('B구역', result)
        self.assertIn('전기 화재인 경우', result)
        self.assertIn('물을 사용하지', result)
        self.assertNotIn('환기', result)

    def test_duplicate_removal_keeps_different_conditions_and_prohibitions(self):
        result = without_repeated_guidance(
            '1. 동쪽 출구로 대피하십시오.\n- 물을 사용하지 마십시오.\n문이 막힌 경우 서쪽 출구로 대피하십시오.',
            '- 동쪽 출구로 대피하십시오.')
        self.assertNotIn('동쪽', result)
        self.assertIn('사용하지', result)
        self.assertIn('문이 막힌 경우', result)
    def test_keeps_different_passages_from_same_manual(self):
        documents = [
            {"source": "manual.pdf", "page_content": "### 대피 가능한 경우\n계단으로 대피하십시오."},
            {"source": "manual.pdf", "page_content": "### 대피 어려운 경우\n문을 닫고 구조를 요청하십시오."},
        ]
        result = build_manual_context(documents)
        self.assertIn("대피 가능한 경우", result)
        self.assertIn("대피 어려운 경우", result)
        self.assertIn("구조를 요청하십시오.", result)

    def test_only_removes_metadata_and_duplicate_content(self):
        documents = [
            {"source": "a", "page_content": "### [위치: 공장]\n[출처: a]\n---\n### 전기 화재\n물을 사용하지 마십시오."},
            {"source": "b", "page_content": "전기 화재\n물을 사용하지 마십시오."},
        ]
        self.assertEqual(build_manual_context(documents), "전기 화재\n물을 사용하지 마십시오.")

    def test_empty_first_passage_does_not_hide_second(self):
        self.assertEqual(build_manual_context([
            {"source": "a", "page_content": "[출처: a]"},
            {"source": "a", "page_content": "119에 신고하십시오."},
        ]), "119에 신고하십시오.")


if __name__ == "__main__":
    unittest.main()
