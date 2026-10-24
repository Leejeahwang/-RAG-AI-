"""대시보드 앱 실행 테스트 (Streamlit AppTest): 관제사 질의 전송·거절, 화면 예외 없음.

브라우저 클릭은 배너가 생기고 사라지며 화면이 움직이면 결과가 흔들린다. 여기서는 위젯에
값을 직접 넣고 버튼을 눌러 전송 로직 자체를 검증한다."""
import os
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakeQA:
    def invoke(self, prompt, layout_text="", emergency=False):
        return {"result": f"답변: {prompt}", "provider": "ollama", "fallback_reason": ""}


@unittest.skipUnless(__import__("importlib").util.find_spec("streamlit"), "streamlit 없음")
class DashboardAppTests(unittest.TestCase):
    def setUp(self):
        from streamlit.testing.v1 import AppTest
        from gui import workers as W
        from gui.state import RUNTIME
        self.W, self.RUNTIME = W, RUNTIME
        os.environ["MQTT_BROKER_PORT"] = "1"       # 브로커 없이
        os.environ["STT_ENABLED"] = "false"
        p = patch.object(W, "NativeQA", _FakeQA)
        p.start(); self.addCleanup(p.stop)
        q = patch.object(W, "enqueue_query")       # 실제 LLM 큐 대신 호출만 기록
        self.enqueue = q.start(); self.addCleanup(q.stop)
        self.at = AppTest.from_file(os.path.join(ROOT, "gui", "dashboard.py"), default_timeout=60)
        self.at.session_state["active_zone"] = "A"
        self.at.run()

    def _send(self, text):
        self.at.text_input(key="query_input").input(text)
        self.at.button(key="query_send").click()
        self.at.run()

    def test_renders_without_exception(self):
        self.assertEqual([e.value for e in self.at.exception], [])

    def test_successful_send_clears_input(self):
        self.RUNTIME.set_generating(False)
        self._send("소화기 위치")
        self.enqueue.assert_called_once()
        self.assertEqual(self.enqueue.call_args.args[1], "소화기 위치")
        self.assertEqual(self.at.text_input(key="query_input").value, "")
        self.assertTrue(any("질의 전송 완료" in s.value for s in self.at.success))
        self.assertTrue(any("관제사 질의: 소화기 위치" in l for l in self.RUNTIME.snapshot_logs()))

    def test_send_while_busy_keeps_question(self):
        self.RUNTIME.set_generating(True)
        self.addCleanup(self.RUNTIME.set_generating, False)
        self._send("두번째 질문")
        self.enqueue.assert_not_called()
        self.assertEqual(self.at.text_input(key="query_input").value, "두번째 질문")
        self.assertTrue(any("다른 질문을 처리 중" in w.value for w in self.at.warning))

    def test_empty_send_warns(self):
        self._send("   ")
        self.enqueue.assert_not_called()
        self.assertTrue(any("질문을 입력해 주세요" in w.value for w in self.at.warning))

    def test_consecutive_sends_are_separate(self):
        self.RUNTIME.set_generating(False)
        self._send("질문1")
        self._send("질문2")
        self.assertEqual([c.args[1] for c in self.enqueue.call_args_list], ["질문1", "질문2"])


if __name__ == "__main__":
    unittest.main()
