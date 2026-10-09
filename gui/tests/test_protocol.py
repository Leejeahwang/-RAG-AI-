"""메시지 형식 단위 테스트: build → parse 왕복, 잘못된 입력 처리."""
import json
import unittest

from gui import mqtt_settings as S
from gui.protocol import (
    AIState, build_event, build_online, build_status,
    parse_event, parse_online, parse_status, provider_label,
)

# main.py _monitor_once 에서 실제로 나오는 모양
TEMP = {"temperature": 75.0, "humidity": 41.2}
RISK = {"level": 5, "label": "재난", "details": "🚨 대형 재난 화재 확정!", "is_early_detection": False}
ANALYSIS = {
    "fire_detected": True, "confidence": 0.86, "description": "🚨 [로컬 감지]",
    "is_real_smoke": False, "is_static_photo": False, "detected_classes": ["FIRE"],
    "status": "REAL_FIRE_FLICKERING", "box": [1, 2, 3, 4],
}


class TopicTests(unittest.TestCase):
    def test_topic_roundtrip(self):
        self.assertEqual(S.split_topic(S.topic("A", "status")), ("A", "status"))
        self.assertEqual(S.subscribe_pattern(), f"{S.TOPIC_PREFIX}/+/+")

    def test_unknown_topics_ignored(self):
        for bad in ("factory/sensors/A", f"{S.TOPIC_PREFIX}/A/unknown", f"{S.TOPIC_PREFIX}//status",
                    f"{S.TOPIC_PREFIX}/A/status/extra", ""):
            self.assertIsNone(S.split_topic(bad), bad)


class StatusTests(unittest.TestCase):
    def test_roundtrip_keeps_pi_values(self):
        ai = AIState("대피하십시오", "ollama", "ConnectTimeout", 123.0)
        raw = build_status("A", sensor_mode="demo", temp=TEMP, gas=600, smoke=550,
                           risk=RISK, level=5, analysis=ANALYSIS, alarm=True, ai=ai, ts=10.0)
        msg = parse_status(raw, "A")
        self.assertEqual((msg.zone, msg.ts, msg.sensor_mode, msg.alarm), ("A", 10.0, "demo", True))
        self.assertEqual((msg.sensors.gas, msg.sensors.smoke, msg.sensors.temperature), (600, 550, 75.0))
        self.assertEqual((msg.risk.level, msg.risk.fused_level, msg.risk.label), (5, 5, "재난"))
        self.assertEqual(msg.vision.status, "REAL_FIRE_FLICKERING")
        self.assertTrue(msg.vision.fire_detected)
        self.assertFalse(msg.vision.photo_blocked)
        self.assertEqual(msg.ai, ai)

    def test_shown_level_differs_from_fused_during_alarm(self):
        # 경보 중 main.py 는 current_level 을 경보 시작 단계 이상으로 유지한다
        raw = build_status("A", sensor_mode="demo", temp=TEMP, gas=0, smoke=0,
                           risk={"level": 0, "details": ""}, level=5, analysis={}, alarm=True, ai=AIState())
        msg = parse_status(raw, "A")
        self.assertEqual((msg.risk.level, msg.risk.fused_level, msg.risk.label), (5, 0, "재난"))

    def test_camera_offline_analysis(self):
        raw = build_status("A", sensor_mode="hardware", temp=TEMP, gas=0, smoke=0, risk=RISK, level=0,
                           analysis={"status": "CAMERA_OFFLINE", "fire_detected": False},
                           alarm=False, ai=AIState())
        msg = parse_status(raw, "A")
        self.assertTrue(msg.vision.camera_offline)
        self.assertEqual(msg.vision.confidence, 0.0)

    def test_photo_blocked_only_for_motion_statuses(self):
        for status, expected in [("STATIC_PHOTO_BLOCKED", True), ("HANDHELD_PHOTO_BLOCKED", True),
                                 ("SAFE", False), ("EVALUATING_FIRE_MOTION", False)]:
            raw = json.dumps({"vision": {"status": status, "static_photo": True}})
            self.assertEqual(parse_status(raw, "A").vision.photo_blocked, expected, status)

    def test_missing_and_wrong_types_use_defaults(self):
        raw = json.dumps({"sensors": {"gas": "abc", "smoke": None}, "risk": {"level": 9},
                          "vision": "oops", "alarm": "true"})
        msg = parse_status(raw, "B")
        self.assertEqual((msg.sensors.gas, msg.sensors.smoke), (0, 0))
        self.assertEqual(msg.risk.level, 5)          # 0~5 로 제한
        self.assertEqual(msg.risk.label, "재난")
        self.assertEqual(msg.vision.status, "")
        self.assertTrue(msg.alarm)
        self.assertEqual(parse_status(json.dumps({"risk": {"level": -3}}), "B").risk.level, 0)

    def test_broken_json_raises_value_error(self):
        for bad in (b"{", b"[]", b"\xff\xd8\xff", "null"):
            with self.assertRaises(ValueError):
                parse_status(bad, "A")


class EventTests(unittest.TestCase):
    def test_event_roundtrip(self):
        raw = build_event("A", 3, "guidance", ts=5.0, text="t", provider="gemini",
                          fallback_reason="", emergency=True, level=None)
        ev = parse_event(raw, "A")
        self.assertEqual((ev.seq, ev.type, ev.text, ev.provider, ev.emergency, ev.ts),
                         (3, "guidance", "t", "gemini", True, 5.0))
        self.assertNotIn("level", json.loads(raw))

    def test_unknown_event_type(self):
        with self.assertRaises(ValueError):
            build_event("A", 1, "explode")
        with self.assertRaises(ValueError):
            parse_event(json.dumps({"type": "explode"}), "A")

    def test_online(self):
        self.assertFalse(parse_online(build_online("C", False), "C").online)
        self.assertTrue(parse_online(build_online("C", True), "C").online)

    def test_provider_labels(self):
        self.assertEqual(provider_label("ollama"), "로컬 Qwen")
        self.assertEqual(provider_label("fixed"), "고정 안내")
        self.assertEqual(provider_label("something"), "something")
        self.assertEqual(provider_label(""), "-")


if __name__ == "__main__":
    unittest.main()
