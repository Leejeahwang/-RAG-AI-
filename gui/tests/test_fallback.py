"""Fallback 재시도 카운트다운: Pi 의 AI 모드·Gemini 재시도 대기 → status → 대시보드 표시."""
import json
import time
import unittest
from unittest.mock import patch

from gui import edge_publisher as E
from gui import fake_edge
from gui import workers as W
from gui.protocol import AIState, ProviderState, build_status, parse_status
from gui.state import RuntimeState
from gui.tests.test_edge_publisher import TEMP, FakeClient, make_pub, monitor


def status_with(provider):
    return build_status("A", sensor_mode="demo", temp=TEMP, gas=0, smoke=0, risk={"level": 0},
                        level=0, analysis={}, alarm=False, ai=AIState(), provider=provider)


class ProtocolTests(unittest.TestCase):
    def test_roundtrip(self):
        pv = ProviderState(mode="auto", gemini_key=True, retry_in=42.04, cooldown=60)
        got = parse_status(status_with(pv), "A").provider
        self.assertEqual((got.mode, got.gemini_key, got.retry_in, got.cooldown), ("auto", True, 42.0, 60.0))
        self.assertTrue(got.known and got.cooling)

    def test_old_pi_without_provider(self):
        raw = status_with(None)
        self.assertNotIn("provider", json.loads(raw))
        got = parse_status(raw, "A").provider
        self.assertFalse(got.known)
        self.assertFalse(got.cooling)

    def test_bad_values(self):
        raw = json.dumps({"provider": {"mode": "AUTO", "retry_in": -5, "cooldown": "x", "gemini_key": "false"}})
        got = parse_status(raw, "A").provider
        self.assertEqual((got.mode, got.retry_in, got.cooldown, got.gemini_key), ("auto", 0.0, 0.0, False))


class ReadProviderStateTests(unittest.TestCase):
    def setUp(self):
        from rag import provider as P
        self.P = P
        self.addCleanup(setattr, P, "_failure_until", P._failure_until)
        mode = P.get_ai_mode()
        self.addCleanup(P.set_ai_mode, mode)

    def test_reads_real_provider_module(self):
        self.P.set_ai_mode("auto")
        self.assertEqual(E.read_provider_state().retry_in, 0.0)
        self.P._failure_until = time.monotonic() + 42
        state = E.read_provider_state()
        self.assertEqual(state.mode, "auto")
        self.assertAlmostEqual(state.retry_in, 42, delta=1)
        self.assertGreater(state.cooldown, 0)

    def test_cooldown_only_counts_in_auto_mode(self):
        self.P.set_ai_mode("gemini")
        self.P._failure_until = time.monotonic() + 42      # set_ai_mode 가 0 으로 돌려놓으므로 뒤에 설정
        self.assertEqual(E.read_provider_state().retry_in, 0.0)


class PublisherTests(unittest.TestCase):
    def test_status_carries_provider_and_cooling_change_is_immediate(self):
        client = FakeClient()
        state = {"pv": ProviderState("auto", True, 0.0, 60.0)}
        pub = make_pub(client, status_interval=10.0)
        pub.provider_state = lambda: state["pv"]
        monitor(pub)
        monitor(pub)                                     # 같은 상태 → 발행 안 함
        state["pv"] = ProviderState("auto", True, 60.0, 60.0)
        monitor(pub)                                     # 재시도 대기 시작 → 즉시
        state["pv"] = ProviderState("local", True, 0.0, 60.0)
        monitor(pub)                                     # 모드 변경 → 즉시
        statuses = [json.loads(p) for t, p, *_ in client.published if t.endswith("/status")]
        self.assertEqual([s["provider"]["mode"] for s in statuses], ["auto", "auto", "local"])
        self.assertEqual(statuses[1]["provider"]["retry_in"], 60.0)

    def test_provider_failure_does_not_block_status(self):
        client = FakeClient()
        pub = make_pub(client)
        pub.provider_state = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        monitor(pub, 5, True)
        statuses = [json.loads(p) for t, p, *_ in client.published if t.endswith("/status")]
        self.assertEqual(len(statuses), 1)
        self.assertNotIn("provider", statuses[0])
        self.assertTrue(statuses[0]["alarm"])


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.rt = RuntimeState()
        p = patch.object(W, "RUNTIME", self.rt)
        p.start()
        self.addCleanup(p.stop)

    def test_countdown_decreases_with_receive_time(self):
        from gui import components as C
        W.handle_message("edge/A/status", status_with(ProviderState("auto", True, 42.0, 60.0)), rx=1000.0)
        v = self.rt.get_zone("A")
        self.assertAlmostEqual(C.retry_left(v, now=1000.0), 42.0)
        self.assertAlmostEqual(C.retry_left(v, now=1010.0), 32.0)
        self.assertEqual(C.retry_left(v, now=1100.0), 0.0)

    def test_transition_logs(self):
        W.handle_message("edge/A/status", status_with(ProviderState("auto", True, 0.0, 60.0)))
        W.handle_message("edge/A/status", status_with(ProviderState("auto", True, 60.0, 60.0)))
        W.handle_message("edge/A/status", status_with(ProviderState("auto", True, 0.0, 60.0)))
        W.handle_message("edge/A/status", status_with(ProviderState("local", True, 0.0, 60.0)))
        logs = "\n".join(self.rt.snapshot_logs())
        self.assertIn("Gemini 실패", logs)
        self.assertIn("재시도 대기 종료", logs)
        self.assertIn("auto → local", logs)


class FakeEdgeScenarioTests(unittest.TestCase):
    def test_second_fire_during_cooldown_reports_waiting(self):
        rt = RuntimeState()
        reasons = []
        client = FakeClient(sink=lambda t, p: W.handle_message(t, p))
        # 시나리오 한 바퀴(약 63초)가 기본 대기 60초보다 길어져, 2회차가 대기 안에 들도록 대기를 늘린다
        with patch.object(W, "RUNTIME", rt), patch.object(fake_edge, "TICK", 0.01),                 patch.object(fake_edge, "GEMINI_COOLDOWN", 120.0):
            edge = fake_edge.FakeEdge("A", "127.0.0.1", 1883)
            edge.pub = make_pub(client, status_interval=0.05, frame_fps=0)
            for _ in range(2):                                   # 시나리오 2회 (약 63초 × 2, 대기 120초)
                for phase in fake_edge.scenario("A"):
                    edge.run_phase(phase, speed=40)
            edge.pub.close()
        reasons = [e.fallback_reason for e in rt.get_zone("A").events
                   if e.type == "guidance" and e.provider == "ollama"]
        self.assertEqual(reasons, ["ConnectTimeout", "Gemini 재시도 대기 중"])


if __name__ == "__main__":
    unittest.main()
