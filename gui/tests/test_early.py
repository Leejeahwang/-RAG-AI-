"""Level 2 조기 알림: 비전 감지 → 센서 반응 선행 시간."""
import unittest
from unittest.mock import patch

from gui import fake_edge
from gui import workers as W
from gui.early import CLEAR_SECONDS, IDLE, REACTED, WAITING, EarlyTracker, sensors_over, vision_first
from gui.protocol import Risk, Sensors, StatusMsg, Vision
from gui.state import RuntimeState
from gui.tests.test_edge_publisher import FakeClient, make_pub

NORMAL = Sensors(temperature=24.0, gas=125, smoke=80)
HOT = Sensors(temperature=75.0, gas=600, smoke=550)


def st(ts, *, sensors=NORMAL, smoke=False, fire=False, early=None, photo=False, status=None, alarm=False):
    vision = Vision(status=status or ("STATIC_PHOTO_BLOCKED" if photo else "SAFE"),
                    fire_detected=fire, real_smoke=smoke, static_photo=photo)
    return StatusMsg(zone="A", ts=ts, sensors=sensors, vision=vision,
                     risk=Risk(early=smoke if early is None else early), alarm=alarm)


class ConditionTests(unittest.TestCase):
    def test_vision_first(self):
        self.assertTrue(vision_first(st(0, smoke=True)))
        self.assertTrue(vision_first(st(0, fire=True)))
        self.assertFalse(vision_first(st(0)))
        self.assertFalse(vision_first(st(0, fire=True, photo=True)))          # 사진 오탐 차단은 제외
        self.assertFalse(vision_first(st(0, fire=True, status="CAMERA_OFFLINE")))

    def test_sensors_over_uses_strict_greater(self):
        th = {"smoke_mq2": 300, "gas_mq135": 400, "temperature_high": 60}
        self.assertEqual(sensors_over(st(0, sensors=Sensors(60.0, 0, 400, 300)), th), ())
        self.assertEqual(sensors_over(st(0, sensors=Sensors(60.1, 0, 401, 301)), th), ("연기", "가스", "온도"))


class TrackerTests(unittest.TestCase):
    def test_vision_then_sensor_measures_lead_in_pi_time(self):
        t = EarlyTracker()
        self.assertIn("조기 감지", t.update(st(100.0, smoke=True), rx=5000.0))
        self.assertEqual(t.phase, WAITING)
        self.assertEqual(t.view().since_rx, 5000.0)
        self.assertIsNone(t.update(st(104.0, smoke=True), rx=5004.0))
        note = t.update(st(118.4, smoke=True, sensors=HOT), rx=5099.0)      # 관제 PC 시각이 크게 달라도
        self.assertIn("18.4초", note)                                       # Pi 시각끼리 계산
        self.assertEqual(t.phase, REACTED)
        last = t.view().last
        self.assertAlmostEqual(last.lead, 18.4)
        self.assertEqual(last.sensors, ("연기", "가스", "온도"))

    def test_sensor_first_is_not_measured(self):
        t = EarlyTracker()
        self.assertIsNone(t.update(st(100.0, fire=True, sensors=HOT), rx=1.0))
        self.assertEqual(t.phase, IDLE)
        self.assertEqual(t.view().results, ())

    def test_vision_disappears_without_sensor(self):
        t = EarlyTracker()
        t.update(st(100.0, smoke=True), rx=0.0)
        self.assertIsNone(t.update(st(105.0), rx=5.0))                       # 잠깐 사라짐 → 계속 대기
        self.assertEqual(t.phase, WAITING)
        note = t.update(st(112.0), rx=CLEAR_SECONDS + 0.5)
        self.assertIn("센서 반응 없이", note)
        self.assertEqual(t.phase, IDLE)
        self.assertIsNone(t.view().last.lead)

    def test_reacted_returns_to_idle_after_quiet_period(self):
        t = EarlyTracker()
        t.update(st(0.0, smoke=True), rx=0.0)
        t.update(st(5.0, fire=True, sensors=HOT, alarm=True), rx=5.0)
        t.update(st(20.0, alarm=True), rx=20.0)                              # 경보 중이면 유지
        self.assertEqual(t.phase, REACTED)
        t.update(st(23.0), rx=23.0)
        self.assertEqual(t.phase, REACTED)                                   # 3초: 아직
        t.update(st(26.0), rx=26.0)
        self.assertEqual(t.phase, IDLE)                                      # 6초 > REARM_SECONDS
        t.update(st(40.0, smoke=True), rx=40.0)                              # 다음 측정 시작
        self.assertEqual(t.phase, WAITING)
        self.assertEqual(len(t.view().results), 1)


class DashboardScenarioTests(unittest.TestCase):
    def test_fake_edge_early_smoke_then_fire(self):
        """가짜 Pi: 조기 연기 8초 → 화재(센서 상승). 선행 시간 ≈ 8초."""
        rt = RuntimeState()
        client = FakeClient(sink=lambda t, p: W.handle_message(t, p))
        with patch.object(W, "RUNTIME", rt), patch.object(fake_edge, "TICK", 0.01):
            edge = fake_edge.FakeEdge("A", "127.0.0.1", 1883)
            edge.pub = make_pub(client, status_interval=0.0, frame_fps=0)
            for phase in fake_edge.scenario("A")[:4]:                          # 정상 → 사진 → 조기 연기 → 화재
                edge.run_phase(phase, speed=8)
            edge.pub.close()
        v = rt.get_zone("A")
        last = v.early.last
        self.assertIsNotNone(last)
        # fake_edge 의 ts 는 실제 시각이라 배속을 되돌려 시나리오 초로 비교 (8초 ÷ 8배속 = 1초)
        self.assertAlmostEqual(last.lead * 8, 8.0, delta=1.5)
        logs = "\n".join(rt.snapshot_logs())
        self.assertIn("센서 반응", logs)


if __name__ == "__main__":
    unittest.main()
