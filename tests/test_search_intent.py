import unittest

from rag.search_intent import medical_intent


class SearchIntentTests(unittest.TestCase):
    def test_colloquial_absent_breathing_and_consciousness(self):
        for question in ("사람이 숨을 안쉬는데 어떡해?", "숨을 안 쉰다", "호흡이 없어요", "의식이 없어요"):
            with self.subTest(question=question):
                self.assertEqual(medical_intent(question), "cpr")

    def test_smoke_exposure_is_not_absent_breathing(self):
        self.assertIsNone(medical_intent("연기 때문에 숨쉬기 어려워요"))

    def test_other_medical_topics(self):
        self.assertEqual(medical_intent("피가 멈추지 않아요"), "bleeding")
        self.assertEqual(medical_intent("뼈가 부러진 것 같아요"), "injury")


if __name__ == "__main__":
    unittest.main()
