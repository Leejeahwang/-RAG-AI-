"""
gui/fake_edge.py
================
PC 테스트용 가짜 Pi. 실제 Pi 와 같은 EdgePublisher 로 같은 형식의 메시지를 보낸다.

시나리오:
    정상 → 사진 오탐 차단 → 조기 연기(LV2) → 화재(LV5, 첫 고정 안내)
    → Gemini 실패로 로컬 Qwen 지침 → 카메라 오프라인 → 정상 복귀

실행 (프로젝트 루트에서):
    mosquitto -v                                   # 브로커 (별도 창)
    python -m gui.fake_edge                        # A구역 1회
    python -m gui.fake_edge --zone B --loop        # B구역 반복
    streamlit run gui/dashboard.py                 # 대시보드
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from gui import mqtt_settings as S
from gui.edge_publisher import EdgePublisher
from gui.protocol import EVENT_ALARM_END, EVENT_ALARM_START, EVENT_GUIDANCE

# rag/provider.py EMERGENCY_GUIDANCE 와 같은 문장 (Pi 를 흉내 내기 위해 복사)
FIRST_GUIDANCE = (
    "화재 위험이 감지되었습니다. 안전한 대피가 가능하면 즉시 대피하십시오. "
    "대피가 어렵다면 119에 현재 위치를 알리고 구조를 요청하십시오."
)
LOCAL_GUIDANCE = (
    "{zone}구역 화재입니다. 자세를 낮추고 젖은 천으로 코와 입을 막으십시오. "
    "엘리베이터를 사용하지 말고 가장 가까운 비상구 계단으로 대피하십시오."
)

TICK = 0.15   # main.py MONITOR_INTERVAL 과 같은 감시 주기


@dataclass
class Phase:
    name: str
    seconds: float
    smoke: int
    gas: int
    temp: float
    vision: dict
    level: int
    details: str
    early: bool = False
    frame: str = "normal"          # normal | photo | smoke | fire | none
    on_enter: Optional[Callable[["FakeEdge"], None]] = None
    at: Optional[tuple] = None     # (초, 콜백) 단계 중간 이벤트


def _vision(status: str, fire=False, smoke=False, photo=False, conf=0.0, desc="", box=None) -> dict:
    return {"status": status, "fire_detected": fire, "is_real_smoke": smoke,
            "is_static_photo": photo, "confidence": conf, "description": desc, "box": box}


def _risk_of(level: int, details: str, early: bool) -> dict:
    labels = {0: "정상", 1: "주의", 2: "경고", 3: "위험", 4: "긴급", 5: "재난"}
    return {"level": level, "label": labels[level], "details": details, "is_early_detection": early}


class FakeEdge:
    def __init__(self, zone: str, host: str, port: int, sensor_mode: str = "demo"):
        self.zone = zone
        self.pub = EdgePublisher(zone, sensor_mode=sensor_mode, host=host, port=port, enabled=True)
        self.alarm = False
        self.alarm_level = 0
        self._t0 = time.monotonic()

    # ── 이벤트 (main.py 의 4개 연결 지점과 같은 순서) ──
    def alarm_start(self, level: int, details: str) -> None:
        self.alarm, self.alarm_level = True, level
        self.pub.publish_event(EVENT_ALARM_START, level=level, details=details,
                               text=FIRST_GUIDANCE, provider="fixed")
        print(f"  ▶ alarm_start LV{level}")

    def guidance(self, provider: str, fallback_reason: str, text: str) -> None:
        self.pub.publish_event(EVENT_GUIDANCE, text=text, provider=provider,
                               fallback_reason=fallback_reason, emergency=True)
        print(f"  ▶ guidance {provider} ({fallback_reason or '-'})")

    def alarm_end(self) -> None:
        self.alarm, self.alarm_level = False, 0
        self.pub.publish_event(EVENT_ALARM_END)
        print("  ▶ alarm_end")

    # ── 가짜 카메라 ──
    def frame(self, kind: str, label: str) -> Optional[np.ndarray]:
        import cv2

        if kind == "none":
            return None
        t = time.monotonic() - self._t0
        img = np.full((360, 640, 3), (34, 30, 28), np.uint8)
        cv2.rectangle(img, (0, 250), (640, 360), (50, 46, 44), -1)          # 바닥
        cv2.rectangle(img, (420, 120), (560, 250), (70, 80, 90), -1)        # 설비
        if kind == "photo":
            cv2.rectangle(img, (220, 110), (360, 260), (240, 240, 240), -1)  # 정지 사진
            cv2.circle(img, (290, 200), 30, (0, 120, 255), -1)
        if kind in ("smoke", "fire"):
            for i in range(6):
                y = int(240 - ((t * 40 + i * 30) % 180))
                r = 14 + i * 4
                cv2.circle(img, (300 + int(8 * math.sin(t * 2 + i)), y), r, (150, 150, 150), -1)
        if kind == "fire":
            for i in range(5):
                h = 50 + int(25 * math.sin(t * 9 + i))
                x = 260 + i * 18
                cv2.ellipse(img, (x, 245), (12, h), 0, 180, 360, (0, 90 + i * 25, 255), -1)
        cv2.putText(img, f"FAKE EDGE {self.zone} | {label}", (12, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1, cv2.LINE_AA)
        cv2.putText(img, time.strftime("%H:%M:%S"), (540, 350),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        return img

    # ── 한 단계 실행 ──
    def run_phase(self, p: Phase, speed: float) -> None:
        print(f"[{self.zone}] {p.name} ({p.seconds:.0f}s)")
        if p.on_enter:
            p.on_enter(self)
        start = time.monotonic()
        fired_at = False
        duration = p.seconds / speed
        while time.monotonic() - start < duration:
            elapsed = (time.monotonic() - start) * speed
            if p.at and not fired_at and elapsed >= p.at[0]:
                p.at[1](self)
                fired_at = True
            temp = {"temperature": round(p.temp + random.uniform(-0.3, 0.3), 1),
                    "humidity": round(45 + random.uniform(-0.5, 0.5), 1)}
            gas = p.gas + random.randint(-3, 3)
            smoke = p.smoke + random.randint(-3, 3)
            risk = _risk_of(p.level, p.details, p.early)
            shown = max(p.level, self.alarm_level) if self.alarm else p.level
            self.pub.publish_monitor(
                temp=temp, gas=gas, smoke=smoke, risk=risk, analysis=p.vision,
                level=shown, alarm=self.alarm, frame=self.frame(p.frame, p.name),
            )
            time.sleep(TICK)


def scenario(zone: str) -> list[Phase]:
    box = [240, 130, 360, 260]
    safe = _vision("SAFE", desc="화재나 연기 객체가 감지되지 않았습니다. (안전 구역)")
    return [
        Phase("정상", 8, 80, 125, 24.0, safe, 0, "모든 센서 및 비전 정상"),
        Phase("사진 오탐 차단", 6, 80, 125, 24.0,
              _vision("STATIC_PHOTO_BLOCKED", photo=True, conf=0.71, box=[220, 110, 360, 260],
                      desc="🛡️ [사진 오탐 차단] 정지된 영상/사진 감지 (움직임 없음 - 오경보 차단)"),
              0, "🛡️ 카메라 정지 사진 감지 (움직임 없음 - 오경보 차단 중)", frame="photo"),
        Phase("조기 연기 감지", 8, 140, 150, 25.0,
              _vision("REAL_SMOKE_RISING", fire=True, smoke=True, conf=0.58, box=box,
                      desc="🚨 [조기 감지] 미세 연기 상방 확산 포착 (확신도: 58.0%)"),
              2, "🚨 [비전 조기 감지] 피어오르는 미세 연기 기둥 포착 (센서 도달 전 선제 경보)",
              early=True, frame="smoke"),
        Phase("화재 확정", 10, 550, 600, 75.0,
              _vision("REAL_FIRE_FLICKERING", fire=True, conf=0.86, box=box,
                      desc="🚨 [로컬 감지] 위험 요소: [FIRE, SMOKE] (AI 확신도: 86.0%)"),
              5, "🚨 대형 재난 화재 확정! (비전 감지 + 연기센서(천장), 가스센서, 고온감지)",
              frame="fire",
              on_enter=lambda e: e.alarm_start(5, "🚨 대형 재난 화재 확정! (비전 감지 + 연기센서(천장), 가스센서, 고온감지)"),
              at=(4, lambda e: e.guidance("ollama", "ConnectTimeout", LOCAL_GUIDANCE.format(zone=zone)))),
        Phase("카메라 오프라인", 5, 520, 580, 70.0,
              {"status": "CAMERA_OFFLINE", "fire_detected": False},
              4, "🔥 실제 화재 확정! (카메라 오프라인, 센서 유지)", frame="none"),
        Phase("정상 복귀", 8, 80, 125, 26.0, safe, 0, "모든 센서 및 비전 정상",
              at=(2, lambda e: e.alarm_end())),
    ]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="가짜 Pi 발행기 (대시보드 PC 테스트)")
    ap.add_argument("--zone", default="A", help="구역 ID (기본 A)")
    ap.add_argument("--host", default=S.BROKER_HOST)
    ap.add_argument("--port", type=int, default=S.BROKER_PORT)
    ap.add_argument("--mode", default="demo", choices=["demo", "hardware"], help="보고할 센서 모드")
    ap.add_argument("--speed", type=float, default=1.0, help="시나리오 배속 (2 = 두 배 빠르게)")
    ap.add_argument("--loop", action="store_true", help="시나리오 반복")
    args = ap.parse_args(argv)

    edge = FakeEdge(args.zone.upper(), args.host, args.port, args.mode)
    edge.pub.start()
    deadline = time.monotonic() + 5
    while not edge.pub.connected and time.monotonic() < deadline:
        time.sleep(0.1)
    if not edge.pub.connected:
        print(f"브로커 {args.host}:{args.port} 에 연결하지 못했습니다. mosquitto 실행을 확인하세요.",
              file=sys.stderr)
        edge.pub.close()
        return 1
    print(f"브로커 {args.host}:{args.port} 연결됨 → {S.topic(edge.zone, '#')}")
    try:
        while True:
            for phase in scenario(edge.zone):
                edge.run_phase(phase, max(args.speed, 0.1))
            if not args.loop:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if edge.alarm:
            edge.alarm_end()
        edge.pub.close()
        print("종료 (online=false 발행)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
