"""대시보드 수신 처리: MQTT 메시지 → RUNTIME 구역 상태."""
import json
import time
import unittest
from unittest.mock import patch

from gui import mqtt_settings as S
from gui import workers as W
from gui.protocol import AIState, build_event, build_online, build_status
from gui.state import RuntimeState, STALE_THRESHOLD

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


def status(level=0, alarm=False, **kw):
    return build_status(
        kw.get("zone", "A"), sensor_mode=kw.get("mode", "demo"),
        temp={"temperature": 24.0, "humidity": 40.0}, gas=125, smoke=80,
        risk={"level": level, "details": "d", "is_early_detection": kw.get("early", False)},
        level=level, analysis=kw.get("analysis", {"status": "SAFE"}), alarm=alarm,
        ai=kw.get("ai", AIState()),
    )


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.rt = RuntimeState()
        patcher = patch.object(W, "RUNTIME", self.rt)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_status_creates_connected_zone(self):
        self.assertTrue(W.handle_message(S.topic("A", "status"), status(2, early=True)))
        v = self.rt.get_zone("A")
        self.assertTrue(v.connected)
        self.assertEqual(v.level, 2)
        self.assertTrue(v.status.risk.early)
        self.assertEqual(self.rt.zone_ids(), ["A"])
        self.assertEqual(len(self.rt.get_trend("A")), 1)

    def test_stale_status_is_not_connected_and_level_zero(self):
        W.handle_message(S.topic("A", "status"), status(5, alarm=True),
                         rx=time.time() - STALE_THRESHOLD - 1)
        v = self.rt.get_zone("A")
        self.assertTrue(v.stale)
        self.assertFalse(v.connected)
        self.assertEqual(v.level, 0)       # 끊긴 구역의 옛 위험도를 보여 주지 않는다
        self.assertEqual(self.rt.max_level(), 0)

    def test_last_will_offline(self):
        W.handle_message(S.topic("A", "status"), status(1))
        W.handle_message(S.topic("A", "online"), build_online("A", False))
        self.assertFalse(self.rt.get_zone("A").connected)
        W.handle_message(S.topic("A", "online"), build_online("A", True))
        self.assertTrue(self.rt.get_zone("A").connected)

    def test_event_duplicates_ignored(self):
        raw = build_event("A", 1, "alarm_start", ts=1.0, level=5, details="x")
        self.assertTrue(W.handle_message(S.topic("A", "event"), raw))
        W.handle_message(S.topic("A", "event"), raw)     # QoS1 재전송
        self.assertEqual(len(self.rt.get_zone("A").events), 1)
        self.assertGreater(self.rt.get_zone("A").alarm_since, 0)
        W.handle_message(S.topic("A", "event"), build_event("A", 2, "alarm_end", ts=2.0))
        self.assertEqual(self.rt.get_zone("A").alarm_since, 0)

    def test_alarm_detected_from_status_when_event_missed(self):
        W.handle_message(S.topic("A", "status"), status(4, alarm=True))
        self.assertGreater(self.rt.get_zone("A").alarm_since, 0)
        W.handle_message(S.topic("A", "status"), status(0, alarm=False))
        self.assertEqual(self.rt.get_zone("A").alarm_since, 0)

    def test_frame(self):
        self.assertTrue(W.handle_message(S.topic("A", "frame"), JPEG))
        v = self.rt.get_zone("A")
        self.assertEqual(v.frame, JPEG)
        self.assertTrue(v.frame_live)
        self.assertFalse(W.handle_message(S.topic("A", "frame"), b"not a jpeg"))
        self.assertEqual(self.rt.get_zone("A").frame, JPEG)

    def test_bad_payload_logged_not_raised(self):
        self.assertFalse(W.handle_message(S.topic("A", "status"), b"{broken"))
        self.assertFalse(W.handle_message(S.topic("A", "event"), json.dumps({"type": "?"})))
        self.assertFalse(W.handle_message("factory/sensors/A", status()))
        self.assertTrue(any("형식 오류" in line for line in self.rt.snapshot_logs()))

    def test_multiple_zones_max_level(self):
        W.handle_message(S.topic("A", "status"), status(1))
        W.handle_message(S.topic("B", "status"), status(4, alarm=True, zone="B"))
        self.assertEqual(self.rt.zone_ids(), ["A", "B"])
        self.assertEqual(self.rt.max_level(), 4)


if __name__ == "__main__":
    unittest.main()
