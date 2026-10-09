"""
gui/measure_link.py
===================
Pi ↔ 노트북 MQTT 연동 측정 도구 (관제 노트북에서 실행). 대시보드와 동시에 켜도 된다.

측정 항목
    - 왕복 지연(RTT): 노트북 → Pi 브로커 → 노트북. 시계 동기화 없이 정확.
      Pi→노트북 단방향 지연 ≈ RTT/2 (Pi 안의 main.py→브로커 구간은 같은 기기라 1ms 미만)
    - status 수신 간격·지연(Pi 시각 기준, 두 기기 시계가 맞을 때만 참고)
    - frame 초당 장수·크기
    - 끊김 구간: 브로커 연결 끊김/재연결 시각, status 공백(3초 이상), Pi online/offline

실행 (프로젝트 루트에서)
    python -m gui.measure_link --host 192.168.0.50                 # Ctrl+C 로 종료
    python -m gui.measure_link --host 192.168.0.50 --seconds 60 --csv link.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import threading
import time
from typing import Optional

from gui import mqtt_settings as S

PROBE_TOPIC = f"{S.TOPIC_PREFIX}/_probe/rtt"   # 대시보드는 모르는 kind 라 무시한다
GAP_SECONDS = 3.0


def _pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def _fmt_ms(values: list[float]) -> str:
    if not values:
        return "데이터 없음"
    return (f"중앙값 {statistics.median(values):.1f}ms · p95 {_pct(values, 95):.1f}ms · "
            f"최대 {max(values):.1f}ms (n={len(values)})")


class LinkMeter:
    def __init__(self, host: str, port: int, zone: Optional[str]):
        self.host, self.port, self.zone = host, port, zone
        self.lock = threading.Lock()
        self.t0 = time.time()
        self.rtt: list[float] = []
        self.status_delay: list[float] = []
        self.status_gap: list[float] = []
        self.frames: list[tuple[float, int]] = []
        self.timeline: list[tuple[float, str]] = []
        self.rows: list[dict] = []
        self.pending: dict[int, float] = {}
        self.last_status_rx: dict[str, float] = {}
        self.last_alarm: dict[str, bool] = {}
        self.connected = False
        self.seq = 0

    def note(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        with self.lock:
            self.timeline.append((time.time(), text))
        print(f"[{stamp}] {text}", flush=True)

    # ── MQTT 콜백 ──
    def on_connect(self, client, _u, _f, rc, *_):
        failed = rc.is_failure if hasattr(rc, "is_failure") else rc != 0
        if failed:
            self.note(f"❌ 브로커 연결 거부: {rc}")
            return
        self.connected = True
        client.subscribe(S.subscribe_pattern(), qos=0)
        client.subscribe(PROBE_TOPIC, qos=0)
        self.note(f"🟢 브로커 연결됨 {self.host}:{self.port}")

    def on_disconnect(self, *_):
        if self.connected:
            self.note("🔴 브로커 연결 끊김 (재연결 시도 중)")
        self.connected = False

    def on_message(self, _c, _u, msg):
        rx = time.time()
        if msg.topic == PROBE_TOPIC:
            try:
                seq = int(msg.payload)
            except ValueError:
                return
            with self.lock:
                sent = self.pending.pop(seq, None)
            if sent is not None:
                ms = (time.perf_counter() - sent) * 1000
                with self.lock:
                    self.rtt.append(ms)
                    self.rows.append({"t": round(rx - self.t0, 3), "kind": "rtt", "zone": "", "ms": round(ms, 2)})
            return

        parsed = S.split_topic(msg.topic)
        if parsed is None:
            return
        zone, kind = parsed
        if self.zone and zone != self.zone:
            return
        if kind == S.KIND_FRAME:
            with self.lock:
                self.frames.append((rx, len(msg.payload)))
            return
        try:
            data = json.loads(msg.payload)
        except ValueError:
            return
        if kind == S.KIND_ONLINE:
            self.note(f"{'🟢' if data.get('online') else '🔴'} [{zone}] Pi online={data.get('online')}"
                      f"{' (retained)' if msg.retain else ''}")
        elif kind == S.KIND_EVENT:
            self.note(f"📨 [{zone}] event {data.get('type')} {data.get('provider', '')}".rstrip())
        elif kind == S.KIND_STATUS:
            delay = (rx - float(data.get("ts", rx))) * 1000
            with self.lock:
                prev = self.last_status_rx.get(zone)
                self.last_status_rx[zone] = rx
                if not msg.retain:
                    self.status_delay.append(delay)
                    if prev is not None:
                        self.status_gap.append(rx - prev)
                self.rows.append({"t": round(rx - self.t0, 3), "kind": "status", "zone": zone, "ms": round(delay, 2)})
            if prev is not None and rx - prev >= GAP_SECONDS:
                self.note(f"⏸ [{zone}] status 공백 {rx - prev:.1f}초 후 다시 수신")
            alarm = bool(data.get("alarm"))
            if self.last_alarm.get(zone) != alarm:
                self.last_alarm[zone] = alarm
                level = data.get("risk", {}).get("level")
                self.note(f"{'🚨' if alarm else '✅'} [{zone}] alarm={alarm} LV{level}")

    # ── 왕복 지연 측정 ──
    def probe_loop(self, client, stop: threading.Event) -> None:
        while not stop.wait(1.0):
            if not self.connected:
                continue
            with self.lock:
                self.seq += 1
                seq = self.seq
                self.pending[seq] = time.perf_counter()
                for old in [k for k in self.pending if k < seq - 30]:
                    self.pending.pop(old, None)
            client.publish(PROBE_TOPIC, str(seq), qos=0)

    def report(self) -> None:
        dur = time.time() - self.t0
        with self.lock:
            frames = [f for f in self.frames]
            print("\n================ 측정 결과 ================")
            print(f"측정 시간: {dur:.0f}초 · 브로커 {self.host}:{self.port}")
            print(f"왕복 지연 RTT     : {_fmt_ms(self.rtt)}")
            if self.rtt:
                print(f"  → Pi→노트북 단방향 추정(RTT/2): 약 {statistics.median(self.rtt) / 2:.1f}ms")
            print(f"status 지연(시계 기준): {_fmt_ms(self.status_delay)}")
            print("  ※ 두 기기 시계 차이가 그대로 더해짐. 음수이거나 RTT/2 와 크게 다르면 시계가 안 맞는 것")
            if self.status_gap:
                print(f"status 간격      : 중앙값 {statistics.median(self.status_gap):.2f}초 · 최대 {max(self.status_gap):.1f}초")
            if frames:
                span = max(frames[-1][0] - frames[0][0], 1e-6)
                sizes = [s for _, s in frames]
                print(f"frame            : {len(frames) / span:.1f}장/초 · 평균 {statistics.mean(sizes) / 1024:.1f}KB")
            else:
                print("frame            : 수신 없음 (EDGE_FRAME_FPS=0 이거나 카메라 오프라인)")
            if self.timeline:
                print("사건 기록:")
                for ts, text in self.timeline:
                    print(f"  +{ts - self.t0:7.1f}s  {text}")
        print("===========================================")

    def save_csv(self, path: str) -> None:
        with self.lock, open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["t", "kind", "zone", "ms"])
            w.writeheader()
            w.writerows(self.rows)
            for ts, text in self.timeline:
                w.writerow({"t": round(ts - self.t0, 3), "kind": "event", "zone": "", "ms": text})
        print(f"CSV 저장: {path}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Pi ↔ 노트북 MQTT 연동 측정")
    ap.add_argument("--host", default=S.BROKER_HOST, help="Pi IP (브로커 주소)")
    ap.add_argument("--port", type=int, default=S.BROKER_PORT)
    ap.add_argument("--zone", default=None, help="특정 구역만 (기본: 전체)")
    ap.add_argument("--seconds", type=float, default=0, help="측정 시간. 0이면 Ctrl+C 까지")
    ap.add_argument("--csv", default="", help="결과를 CSV 로 저장할 경로")
    args = ap.parse_args(argv)

    meter = LinkMeter(args.host, args.port, args.zone)
    client = S.new_client(f"edge-saver-meter-{int(time.time())}")
    client.on_connect, client.on_disconnect, client.on_message = meter.on_connect, meter.on_disconnect, meter.on_message
    client.reconnect_delay_set(min_delay=1, max_delay=5)
    client.connect_async(args.host, args.port, keepalive=S.KEEPALIVE)
    client.loop_start()

    stop = threading.Event()
    threading.Thread(target=meter.probe_loop, args=(client, stop), daemon=True).start()
    meter.note(f"측정 시작 → {args.host}:{args.port} (Ctrl+C 로 종료)")
    try:
        if args.seconds > 0:
            stop.wait(args.seconds)
        else:
            while not stop.wait(1.0):
                pass
    except KeyboardInterrupt:
        pass
    stop.set()
    meter.connected = False          # 의도한 종료는 끊김으로 기록하지 않음
    client.disconnect()
    client.loop_stop()
    meter.report()
    if args.csv:
        meter.save_csv(args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
