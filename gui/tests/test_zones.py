"""화재·안내·감지 구역, Level 2 비전 경고, 비상 지침 이어 붙이기 (통합 브랜치 10/10·10/18 반영)."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gui import edge_publisher as E
from gui import workers as W
from gui.history import group_incidents
from gui.protocol import (
    AIState, EventMsg, Zones, build_event, build_status, parse_event, parse_status,
)
from gui.state import RuntimeState
from gui.tests.test_edge_publisher import FakeClient, make_pub, monitor

TEMP = {"temperature": 24.0, "humidity": 40.0}


def status(zones=None, alarm=True, analysis=None):
    return build_status("A", sensor_mode="demo", temp=TEMP, gas=0, smoke=0, risk={"level": 4},
                        level=4, analysis=analysis or {}, alarm=alarm, ai=AIState(), zones=zones)


class ProtocolTests(unittest.TestCase):
    def test_zones_roundtrip_and_remote_fire(self):
        z = parse_status(status(Zones("A", "A", "B")), "A").zones
        self.assertEqual((z.local, z.detection, z.fire), ("A", "A", "B"))
        self.assertTrue(z.remote_fire)
        self.assertFalse(Zones("A", "A", "A").remote_fire)
        self.assertFalse(Zones("A", "A", "").remote_fire)

    def test_old_pi_without_zones(self):
        raw = status(None)
        self.assertNotIn("zones", json.loads(raw))
        self.assertFalse(parse_status(raw, "A").zones.remote_fire)

    def test_event_zones_and_warning_type(self):
        ev = parse_event(build_event("A", 1, "warning", level=2, text="경고", fire_zone="a", local_zone="A"), "A")
        self.assertEqual((ev.type, ev.fire_zone, ev.local_zone), ("warning", "A", "A"))

    def test_demo_bypass_field(self):
        v = parse_status(status(analysis={"status": "DEMO_BYPASS", "demo_bypass": True}), "A").vision
        self.assertTrue(v.demo_bypass)


class PublisherTests(unittest.TestCase):
    def test_status_zones_only_fire_during_alarm(self):
        client = FakeClient()
        pub = make_pub(client, status_interval=0.0)
        pub.detection_zone = "C"
        pub.publish_monitor(temp=TEMP, gas=0, smoke=0, risk={"level": 0}, analysis={}, alarm=False, fire_zone="B")
        pub.publish_monitor(temp=TEMP, gas=0, smoke=0, risk={"level": 4}, analysis={}, alarm=True, fire_zone="B")
        zs = [json.loads(p)["zones"] for t, p, *_ in client.published if t.endswith("/status")]
        self.assertEqual(zs[0], {"local": "A", "detection": "C", "fire": ""})   # 경보가 아니면 화재 구역 없음
        self.assertEqual(zs[1], {"local": "A", "detection": "C", "fire": "B"})

    def test_emergency_guidance_accumulates_like_pi_broadcast(self):
        pub = make_pub(FakeClient())
        pub.publish_event("alarm_start", text="B구역에서 화재 위험", provider="fixed")
        pub.publish_event("guidance", text="A구역 대피로", provider="zone", emergency=True)
        pub.publish_event("guidance", text="일반 답변", provider="gemini", emergency=False)   # 섞이지 않음
        pub.publish_event("guidance", text="추가 수칙", provider="ollama", emergency=True)
        self.assertEqual(pub.ai_state.text, "B구역에서 화재 위험\nA구역 대피로\n추가 수칙")
        self.assertEqual(pub.ai_state.provider, "ollama")
        pub.publish_event("alarm_end")
        self.assertEqual(pub.ai_state.text, "")

    def test_publish_guidance_uses_spoken_text_and_skips_empty(self):
        client = FakeClient()
        with patch.object(E, "_default", make_pub(client)):
            result = SimpleNamespace(text="원문 (중복 포함)", provider="ollama", fallback_reason="")
            E.publish_guidance(result, emergency=True, text="중복 제거 후", fire_zone="B", local_zone="A")
            E.publish_guidance(result, emergency=True, text="")          # 추가 수칙 없음 → 보내지 않음
            E.publish_guidance(SimpleNamespace(text="", provider="fixed"), emergency=True)   # AI 실패 → 안 보냄
            E.publish_guidance(result, emergency=False)                  # 일반 질문은 원문
        events = [json.loads(p) for t, p, *_ in client.published if t.endswith("/event")]
        self.assertEqual([(e["text"], e["emergency"]) for e in events],
                         [("중복 제거 후", True), ("원문 (중복 포함)", False)])
        self.assertEqual((events[0]["fire_zone"], events[0]["local_zone"]), ("B", "A"))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.rt = RuntimeState()
        p = patch.object(W, "RUNTIME", self.rt)
        p.start()
        self.addCleanup(p.stop)

    def test_logs(self):
        W.handle_message("edge/A/event", build_event("A", 1, "warning", ts=1.0, level=2, text="A구역에서 연기"))
        W.handle_message("edge/A/event", build_event("A", 2, "alarm_start", ts=2.0, level=4, details="d",
                                                     fire_zone="B", local_zone="A"))
        logs = "\n".join(self.rt.snapshot_logs())
        self.assertIn("Level 2 비전 경고 방송 — A구역에서 연기", logs)
        self.assertIn("화재 B구역 수신", logs)

    def test_alarm_where_text(self):
        from gui import components as C
        W.handle_message("edge/A/status", status(Zones("A", "A", "B")))
        v = self.rt.get_zone("A")
        self.assertEqual(C._alarm_where(v), "화재 B구역 → A구역 안내 중")
        W.handle_message("edge/A/status", status(Zones("A", "A", "A")))
        self.assertEqual(C._alarm_where(self.rt.get_zone("A")), "화재 A구역")
        W.handle_message("edge/A/status", status(Zones("A", "A", ""), alarm=False))
        self.assertEqual(C._alarm_where(self.rt.get_zone("A")), "")

    def test_vision_message_without_description(self):
        from gui import components as C
        from gui.protocol import Vision
        self.assertIn("검증된 불꽃", C._vision_message(Vision(fire_detected=True, confidence=0.86)))
        self.assertIn("상승하는 연기", C._vision_message(Vision(real_smoke=True)))
        self.assertIn("시연 우회", C._vision_message(Vision(demo_bypass=True)))
        self.assertEqual(C._vision_message(Vision(status="SAFE")), "")
        self.assertIn("예전 문장", C._vision_message(Vision(fire_detected=True, description="예전 문장")))


class HistoryTests(unittest.TestCase):
    def ev(self, seq, ts, type_, **kw):
        return EventMsg(zone="A", ts=ts, seq=seq, type=type_, **kw)

    def test_warning_is_separate_entry_and_does_not_close_alarm(self):
        events = [
            self.ev(1, 10.0, "warning", level=2, text="연기 경고", fire_zone="A"),
            self.ev(2, 20.0, "alarm_start", level=5, text="첫 안내", provider="fixed", fire_zone="A"),
            self.ev(3, 21.0, "warning", level=2, text="또 경고"),     # 경보 중 경고가 와도 경보는 계속
            self.ev(4, 22.0, "guidance", text="A구역 대피로", provider="zone", emergency=True),
        ]
        incs = group_incidents(events, alarm_active=True, alarm_since=1.0)
        alarm = [i for i in incs if i.kind == "alarm"]
        warnings = [i for i in incs if i.kind == "warning"]
        self.assertEqual(len(alarm), 1)
        self.assertTrue(alarm[0].ongoing)
        self.assertEqual([g.provider for g in alarm[0].guidances], ["fixed", "zone"])
        self.assertEqual(len(warnings), 2)
        self.assertTrue(incs[0].ongoing)                                # 진행 중 경보가 맨 위

    def test_remote_fire_zone_kept(self):
        events = [self.ev(1, 5.0, "alarm_start", level=4, fire_zone="B"), self.ev(2, 9.0, "alarm_end")]
        [inc] = group_incidents(events)
        self.assertEqual(inc.fire_zone, "B")


if __name__ == "__main__":
    unittest.main()
