import unittest

from rag.context import build_manual_context


class ContextTests(unittest.TestCase):
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
