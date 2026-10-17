"""경보 이력: event → 경보 1건 단위 묶기."""
import unittest

from gui.history import group_incidents
from gui.protocol import EventMsg


def ev(seq, ts, type_, **kw):
    return EventMsg(zone="A", ts=ts, seq=seq, type=type_, **kw)


START = dict(level=5, details="화재 확정", text="첫 안내", provider="fixed")


class GroupIncidentsTests(unittest.TestCase):
    def test_complete_incident(self):
        events = [
            ev(1, 100.0, "alarm_start", **START),
            ev(2, 104.0, "guidance", text="로컬 지침", provider="ollama",
               fallback_reason="ConnectTimeout", emergency=True),
            ev(3, 189.0, "alarm_end"),
        ]
        [inc] = group_incidents(events)
        self.assertEqual((inc.start_ts, inc.end_ts, inc.level), (100.0, 189.0, 5))
        self.assertFalse(inc.ongoing)
        self.assertEqual(inc.duration(now=10_000), 89.0)          # Pi 시각끼리 계산
        self.assertEqual([g.provider for g in inc.guidances], ["fixed", "ollama"])

    def test_ongoing_uses_dashboard_clock(self):
        events = [ev(1, 100.0, "alarm_start", **START)]
        [inc] = group_incidents(events, alarm_active=True, alarm_since=5000.0)
        self.assertTrue(inc.ongoing)
        self.assertEqual(inc.duration(now=5012.0), 12.0)          # 관제 PC 시각끼리 계산

    def test_latest_first_and_ongoing_on_top(self):
        events = [
            ev(1, 100.0, "alarm_start", **START), ev(2, 150.0, "alarm_end"),
            ev(3, 300.0, "alarm_start", **START), ev(4, 360.0, "alarm_end"),
            ev(5, 500.0, "alarm_start", **START),
        ]
        incs = group_incidents(events, alarm_active=True, alarm_since=1.0)
        self.assertEqual([i.start_ts for i in incs], [500.0, 300.0, 100.0])
        self.assertTrue(incs[0].ongoing)

    def test_general_answers_are_not_incidents(self):
        events = [ev(1, 10.0, "guidance", text="일반 답변", provider="gemini", emergency=False)]
        self.assertEqual(group_incidents(events), [])

    def test_dashboard_started_mid_alarm(self):
        # alarm_start 를 못 받고 status 로만 경보 중임을 안 경우
        [inc] = group_incidents([], alarm_active=True, alarm_since=700.0)
        self.assertIsNone(inc.start_ts)
        self.assertTrue(inc.ongoing)
        self.assertEqual(inc.duration(now=730.0), 30.0)

        # 그 뒤 지침과 종료만 받은 경우
        events = [ev(9, 710.0, "guidance", text="지침", provider="gemini", emergency=True),
                  ev(10, 760.0, "alarm_end")]
        [inc] = group_incidents(events)
        self.assertIsNone(inc.start_ts)
        self.assertEqual(inc.end_ts, 760.0)
        self.assertIsNone(inc.duration(now=800.0))                # 시작을 모르면 지속 시간 없음
        self.assertEqual(len(inc.guidances), 1)

    def test_missed_alarm_end_is_not_left_ongoing(self):
        events = [ev(1, 100.0, "alarm_start", **START)]
        [inc] = group_incidents(events, alarm_active=False)
        self.assertFalse(inc.ongoing)
        self.assertTrue(inc.end_unknown)
        self.assertIsNone(inc.duration(now=999.0))

    def test_new_start_without_end_closes_previous(self):
        events = [ev(1, 100.0, "alarm_start", **START), ev(2, 200.0, "alarm_start", **START)]
        incs = group_incidents(events, alarm_active=True, alarm_since=1.0)
        self.assertEqual(len(incs), 2)
        self.assertEqual(incs[1].end_ts, 200.0)
        self.assertTrue(incs[0].ongoing)

    def test_limit(self):
        events = []
        for n in range(15):
            events += [ev(2 * n, n * 10.0, "alarm_start", **START), ev(2 * n + 1, n * 10.0 + 5, "alarm_end")]
        incs = group_incidents(events, limit=10)
        self.assertEqual(len(incs), 10)
        self.assertEqual(incs[0].start_ts, 140.0)


if __name__ == "__main__":
    unittest.main()
