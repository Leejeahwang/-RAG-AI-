"""Pi 발행기: main.py 를 막지 않는지, 발행 주기·이벤트·종료가 맞는지.

브로커 없이 FakeClient 로 발행 내용을 가로채고, 필요하면 대시보드 수신부(handle_message)로
바로 넘겨 Pi → 대시보드 전체 흐름(loopback)을 확인한다."""
import json
import time
import unittest
from unittest.mock import patch

import numpy as np

from gui import edge_publisher as E
from gui import fake_edge
from gui import mqtt_settings as S
from gui import workers as W
from gui.state import RuntimeState

TEMP = {"temperature": 24.0, "humidity": 40.0}
SAFE = {"status": "SAFE", "fire_detected": False}


class _Info:
    def wait_for_publish(self, timeout=None):
        return True


class FakeClient:
    """paho Client 중 EdgePublisher 가 쓰는 부분만. connect_async 즉시 연결 성공."""

    def __init__(self, sink=None, connect=True):
        self.sink, self.connect = sink, connect
        self.published, self.will = [], None
        self.on_connect = self.on_disconnect = None
        self.loop_running = False

    def will_set(self, topic, payload, qos=0, retain=False):
        self.will = (topic, payload, qos, retain)

    def reconnect_delay_set(self, **_):
        pass

    def max_queued_messages_set(self, _):
        pass

    def connect_async(self, host, port, keepalive=60):
        self.target = (host, port)

    def loop_start(self):
        self.loop_running = True
        if self.connect:
            self.on_connect(self, None, {}, 0)

    def loop_stop(self):
        self.loop_running = False

    def disconnect(self):
        if self.on_disconnect:
            self.on_disconnect(self, None, 0)

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        if self.sink:
            self.sink(topic, payload)
        return _Info()

    def kinds(self):
        return [S.split_topic(t)[1] for t, *_ in self.published]


def make_pub(client, **kw):
    kw.setdefault("status_interval", 1.0)
    kw.setdefault("frame_fps", 0)
    kw.setdefault("enabled", True)
    return E.EdgePublisher("A", client_factory=lambda _cid: client, **kw)


def monitor(pub, level=0, alarm=False, frame=None, early=False):
    pub.publish_monitor(temp=TEMP, gas=125, smoke=80,
                        risk={"level": level, "details": "d", "is_early_detection": early},
                        analysis=SAFE, level=level, alarm=alarm, frame=frame)


class NeverBlocksTests(unittest.TestCase):
    def test_client_creation_failure_is_silent(self):
        def boom(_cid):
            raise RuntimeError("paho missing")
        pub = E.EdgePublisher("A", enabled=True, client_factory=boom)
        monitor(pub, 5, True)
        pub.publish_event("alarm_start", level=5, text="t", provider="fixed")
        pub.close()
        self.assertFalse(pub.connected)

    def test_disabled_does_nothing(self):
        client = FakeClient()
        pub = make_pub(client, enabled=False)
        monitor(pub)
        pub.publish_event("alarm_end")
        self.assertEqual(client.published, [])

    def test_unreachable_broker_returns_immediately(self):
        # 실제 paho 로 아무도 듣지 않는 포트에 연결: 호출 측은 기다리지 않아야 한다
        pub = E.EdgePublisher("A", host="127.0.0.1", port=1, enabled=True, frame_fps=0)
        try:
            frame = np.zeros((240, 320, 3), np.uint8)
            start = time.perf_counter()
            for _ in range(20):
                monitor(pub, 5, True, frame=frame)
                pub.publish_event("guidance", text="t", provider="ollama", emergency=True)
            self.assertLess(time.perf_counter() - start, 0.5)
            self.assertFalse(pub.connected)
        finally:
            start = time.perf_counter()
            pub.close()
            self.assertLess(time.perf_counter() - start, 3.0)

    def test_module_guidance_accepts_partial_result(self):
        # main.py 테스트의 가짜 결과처럼 fallback_reason 이 없어도 예외 없이 발행
        from types import SimpleNamespace
        client = FakeClient()
        with patch.object(E, "_default", make_pub(client)):
            E.publish_guidance(SimpleNamespace(text="answer", provider="test"), emergency=True)
            E.publish_guidance(None)
            E.publish_monitor(bad_kwarg=1)          # 잘못된 인자도 밖으로 던지지 않음
            self.assertEqual(E.get_publisher().ai_state.text, "answer")
        events = [json.loads(p) for t, p, *_ in client.published if t.endswith("/event")]
        self.assertEqual(events[0]["fallback_reason"], "")

    def test_publish_exception_is_swallowed(self):
        client = FakeClient()
        client.publish = lambda *a, **k: (_ for _ in ()).throw(OSError("socket"))
        pub = make_pub(client)
        monitor(pub)                       # 예외가 밖으로 나오면 실패
        pub.publish_event("alarm_end")


class PublishTests(unittest.TestCase):
    def test_online_and_last_will(self):
        client = FakeClient()
        pub = make_pub(client)
        pub.start()
        self.assertEqual(client.will[0], S.topic("A", "online"))
        self.assertFalse(json.loads(client.will[1])["online"])
        self.assertTrue(client.will[3])                          # retained
        topic, payload, _qos, retain = client.published[0]
        self.assertEqual((topic, json.loads(payload)["online"], retain), (S.topic("A", "online"), True, True))
        pub.close()
        topic, payload, _qos, retain = client.published[-1]
        self.assertEqual((topic, json.loads(payload)["online"]), (S.topic("A", "online"), False))

    def test_status_throttled_but_changes_sent_immediately(self):
        client = FakeClient()
        pub = make_pub(client, status_interval=10.0)
        for _ in range(5):
            monitor(pub, 0)
        self.assertEqual(client.kinds().count("status"), 1)
        monitor(pub, 2, early=True)        # 위험도·조기감지 변화 → 즉시
        monitor(pub, 2, early=True)
        monitor(pub, 2, alarm=True, early=True)   # 경보 변화 → 즉시
        self.assertEqual(client.kinds().count("status"), 3)
        status_msgs = [p for t, p, *_ in client.published if t.endswith("/status")]
        self.assertTrue(all(r for t, _p, _q, r in client.published if t.endswith("/status")))
        self.assertTrue(json.loads(status_msgs[-1])["alarm"])

    def test_events_update_ai_in_next_status(self):
        client = FakeClient()
        pub = make_pub(client, status_interval=10.0)
        monitor(pub, 0)
        pub.publish_event("alarm_start", level=5, details="x", text="첫 안내", provider="fixed")
        monitor(pub, 0)                    # 같은 key 지만 이벤트 직후라 즉시 발행
        last = json.loads([p for t, p, *_ in client.published if t.endswith("/status")][-1])
        self.assertEqual((last["ai"]["text"], last["ai"]["provider"]), ("첫 안내", "fixed"))

        pub.publish_event("guidance", text="일반 답변", provider="gemini", emergency=False)
        self.assertEqual(pub.ai_state.text, "첫 안내")       # 일반 질의 답변은 비상 지침을 덮지 않음
        pub.publish_event("guidance", text="로컬 지침", provider="ollama",
                          fallback_reason="ConnectTimeout", emergency=True)
        self.assertEqual((pub.ai_state.provider, pub.ai_state.fallback_reason), ("ollama", "ConnectTimeout"))
        pub.publish_event("alarm_end")
        self.assertEqual(pub.ai_state.text, "")

        events = [json.loads(p) for t, p, *_ in client.published if t.endswith("/event")]
        self.assertEqual([e["seq"] for e in events], [1, 2, 3, 4])
        self.assertTrue(all(q == 1 for t, _p, q, _r in client.published if t.endswith("/event")))

    def test_status_dropped_while_disconnected_events_queued(self):
        client = FakeClient(connect=False)
        pub = make_pub(client)
        monitor(pub, 5, True)
        pub.publish_event("alarm_start", level=5)
        self.assertEqual(client.kinds(), ["event"])          # QoS1 이벤트만 paho 큐로

    def test_frame_thread_sends_jpeg_with_rate_limit(self):
        client = FakeClient()
        pub = make_pub(client, frame_fps=5)
        frame = np.zeros((480, 640, 3), np.uint8)
        try:
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                monitor(pub, 0, frame=frame)
                time.sleep(0.02)
        finally:
            pub.close()
        frames = [p for t, p, *_ in client.published if t.endswith("/frame")]
        self.assertGreaterEqual(len(frames), 2)
        self.assertLessEqual(len(frames), 7)                 # 5fps × 1초 (+여유)
        self.assertEqual(frames[0][:2], b"\xff\xd8")

    def test_encode_frame_resizes_and_draws_box(self):
        import cv2
        frame = np.zeros((480, 640, 3), np.uint8)
        data = E.encode_frame(frame, {"box": [100, 100, 300, 300], "fire_detected": True,
                                      "status": "REAL_FIRE_FLICKERING"}, width=320, quality=60)
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(img.shape[:2], (240, 320))
        self.assertGreater(int(img[50:150, 50, 2].max()), 150)   # 빨간 박스 왼쪽 변 (x=50)
        self.assertIsNone(E.encode_frame(None))
        self.assertIsNone(E.encode_frame(np.zeros((10,), np.uint8)))


class LoopbackScenarioTests(unittest.TestCase):
    """fake_edge 시나리오 전체를 발행기 → 수신부로 바로 흘려 대시보드 상태를 확인."""

    def test_full_scenario(self):
        rt = RuntimeState()
        seen_levels, seen_ai, seen_offline = set(), [], []

        def sink(topic, payload):
            W.handle_message(topic, payload)
            v = rt.get_zone("A")
            if v and v.status:
                seen_levels.add(v.status.risk.level)
                if v.status.vision.camera_offline:
                    seen_offline.append(v.status.risk.level)
                if v.status.ai.text and (not seen_ai or seen_ai[-1] != v.status.ai.provider):
                    seen_ai.append(v.status.ai.provider)

        client = FakeClient(sink=sink)
        with patch.object(W, "RUNTIME", rt), patch.object(fake_edge, "TICK", 0.01):
            edge = fake_edge.FakeEdge("A", "127.0.0.1", 1883)
            edge.pub = make_pub(client, status_interval=0.05, frame_fps=20)
            try:
                for phase in fake_edge.scenario("A"):
                    edge.run_phase(phase, speed=40)
            finally:
                edge.pub.close()

        v = rt.get_zone("A")
        self.assertEqual([e.type for e in v.events], ["alarm_start", "guidance", "alarm_end"])
        self.assertEqual(seen_levels, {0, 2, 5})
        # 카메라 오프라인 단계(fusion LV4)도 경보 중이라 시작 단계 LV5 유지 (main.py 와 동일)
        self.assertTrue(seen_offline)
        self.assertEqual(set(seen_offline), {5})
        self.assertEqual(seen_ai, ["fixed", "ollama"])
        self.assertEqual(v.status.risk.level, 0)
        self.assertFalse(v.status.alarm)
        self.assertEqual(v.alarm_since, 0)
        self.assertFalse(v.online)                           # close() → online=false
        self.assertIsNotNone(v.frame)


if __name__ == "__main__":
    unittest.main()
