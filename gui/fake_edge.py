"""
gui/fake_edge.py
================
PC 테스트용 가짜 Pi. 실제 Pi 와 같은 EdgePublisher 로 같은 형식의 메시지를 보낸다.

시나리오:
    정상 → 사진 오탐 차단 → 조기 연기(LV2, Level 2 경고 방송) → 화재(LV5, 첫 고정 안내·구역 대피로)
    → Gemini 실패로 로컬 Qwen 지침 (이후 60초 Gemini 재시도 대기) → 카메라 오프라인 → 정상 복귀
    → 다른 구역(B) 화재 경보 수신 (이 구역은 정상이지만 경보·방송) → 정상
    --loop 로 반복하면 2회차 화재는 재시도 대기 중이라 "Gemini 재시도 대기 중" 으로 로컬 지침

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
from gui.protocol import EVENT_ALARM_END, EVENT_ALARM_START, EVENT_GUIDANCE, EVENT_WARNING, ProviderState

# rag/provider.py EMERGENCY_GUIDANCE 와 같은 문장 (Pi 를 흉내 내기 위해 복사)
FIRST_GUIDANCE = (
    "화재 위험이 감지되었습니다. 안전한 대피가 가능하면 즉시 대피하십시오. "
    "대피가 어렵다면 119에 현재 위치를 알리고 구조를 요청하십시오."
)
LOCAL_GUIDANCE = (
    "자세를 낮추고 젖은 천으로 코와 입을 막으십시오. "
    "엘리베이터를 사용하지 말고 연기가 없는 계단으로 이동하십시오."
)
# main.py 의 구역 대피로(rag.layout.evacuation_for_zone)와 Level 2 경고 문장 흉내
ZONE_ROUTE = "{local}구역 대피로: 중앙 통로를 따라 {exit} 비상구로 대피하십시오."
WARNING_SMOKE = "{zone}구역에서 상승하는 연기가 감지되었습니다. 화재 가능성에 주의하고 안전한 곳으로 이동하십시오."

TICK = 0.15   # main.py MONITOR_INTERVAL 과 같은 감시 주기
GEMINI_COOLDOWN = 60.0   # config.GEMINI_RETRY_COOLDOWN 기본값


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
        self.fire_zone = ""
        self._t0 = time.monotonic()
        # rag/provider.py 흉내: auto 모드, Gemini 실패 시 60초 동안 로컬만 사용
        self.ai_mode = "auto"
        self.speed = 1.0
        self._gemini_retry_at = 0.0

    def provider_state(self) -> ProviderState:
        left = max(0.0, (self._gemini_retry_at - time.monotonic()) * self.speed)   # 시나리오 시간(초)
        return ProviderState(mode=self.ai_mode, gemini_key=True, retry_in=left, cooldown=GEMINI_COOLDOWN)

    def gemini_fallback(self, text: str) -> None:
        """Gemini 가 실패해 로컬 Qwen 으로 답한 상황. 재시도 대기 중이면 Gemini 를 부르지 않는다."""
        if self.provider_state().cooling:
            self.guidance("ollama", "Gemini 재시도 대기 중", text)
        else:
            self._gemini_retry_at = time.monotonic() + GEMINI_COOLDOWN / self.speed
            self.guidance("ollama", "ConnectTimeout", text)

    # ── 이벤트 (main.py 의 연결 지점과 같은 순서) ──
    def alarm_start(self, level: int, details: str, fire_zone: Optional[str] = None) -> None:
        """main.py _trigger_rag_alert: 첫 고정 안내("B구역에서 …") → 구역 대피로 안내."""
        fire_zone = fire_zone or self.zone
        self.alarm, self.alarm_level, self.fire_zone = True, level, fire_zone
        self.pub.publish_event(EVENT_ALARM_START, level=level, details=details,
                               text=f"{fire_zone}구역에서 {FIRST_GUIDANCE}", provider="fixed",
                               fire_zone=fire_zone, local_zone=self.zone)
        exit_name = "동쪽" if fire_zone != self.zone else "서쪽"
        self.pub.publish_event(EVENT_GUIDANCE, text=ZONE_ROUTE.format(local=self.zone, exit=exit_name),
                               provider="zone", emergency=True, fire_zone=fire_zone, local_zone=self.zone)
        print(f"  ▶ alarm_start LV{level} (화재 {fire_zone}구역)")

    def warning(self) -> None:
        """main.py _handle_vision_warning: Level 2 고정 경고 음성 1회."""
        self.pub.publish_event(EVENT_WARNING, level=2, details="[비전 조기 감지] 상방 확산 연기 | 센서 반응 전 선제 경고",
                               text=WARNING_SMOKE.format(zone=self.zone), provider="fixed",
                               fire_zone=self.zone, local_zone=self.zone)
        print("  ▶ warning (Level 2)")

    def guidance(self, provider: str, fallback_reason: str, text: str) -> None:
        self.pub.publish_event(EVENT_GUIDANCE, text=text, provider=provider,
                               fallback_reason=fallback_reason, emergency=True,
                               fire_zone=self.fire_zone or self.zone, local_zone=self.zone)
        print(f"  ▶ guidance {provider} ({fallback_reason or '-'})")

    def alarm_end(self) -> None:
        self.alarm, self.alarm_level, self.fire_zone = False, 0, ""
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
        self.speed = speed
        self.pub.provider_state = self.provider_state
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
                level=shown, alarm=self.alarm, fire_zone=self.fire_zone,
                # OpenCV putText 는 한글을 못 그려서 영상 라벨은 영문으로
                frame=self.frame(p.frame, f"{p.frame.upper()} LV{shown}"),
            )
            time.sleep(TICK)


def scenario(zone: str) -> list[Phase]:
    box = [240, 130, 360, 260]
    safe = _vision("SAFE")
    other = "B" if zone != "B" else "C"
    return [
        Phase("정상", 8, 80, 125, 24.0, safe, 0, "모든 센서 및 비전 정상"),
        Phase("사진 오탐 차단", 6, 80, 125, 24.0,
              _vision("STATIC_PHOTO_BLOCKED", photo=True, conf=0.71, box=[220, 110, 360, 260]),
              0, "카메라 사진/강체 오탐 차단 중", frame="photo"),
        Phase("조기 연기 감지", 8, 140, 150, 25.0,
              _vision("REAL_SMOKE_RISING", smoke=True, conf=0.58, box=box),
              2, "[비전 조기 감지] 상방 확산 연기 | 센서 반응 전 선제 경고",
              early=True, frame="smoke", on_enter=lambda e: e.warning()),
        Phase("화재 확정", 10, 550, 600, 75.0,
              _vision("REAL_FIRE_FLICKERING", fire=True, conf=0.86, box=box),
              5, "검증된 불꽃 | 센서 교차 검증: 연기센서(천장), 가스센서, 고온감지",
              frame="fire",
              on_enter=lambda e: e.alarm_start(5, "검증된 불꽃 | 센서 교차 검증: 연기센서(천장), 가스센서, 고온감지"),
              at=(4, lambda e: e.gemini_fallback(LOCAL_GUIDANCE))),
        Phase("카메라 오프라인", 5, 520, 580, 70.0,
              {"status": "CAMERA_OFFLINE", "fire_detected": False},
              3, "센서 복합 반응: 연기센서(천장), 가스센서, 고온감지", frame="none"),
        Phase("정상 복귀", 8, 80, 125, 26.0, safe, 0, "확정된 센서 및 비전 위험 없음",
              at=(2, lambda e: e.alarm_end())),
        # 다른 Pi 의 HTTP 경보 수신 (main.py handle_fire_event): 이 구역 센서·비전은 정상이지만 경보·방송
        Phase(f"{other}구역 화재 수신", 10, 80, 125, 25.0, safe, 0, "확정된 센서 및 비전 위험 없음",
              on_enter=lambda e: e.alarm_start(4, f"검증된 불꽃 | 센서 교차 검증: 고온감지 ({other}구역 노드)",
                                                fire_zone=other),
              at=(7, lambda e: e.alarm_end())),
        Phase("정상", 3, 80, 125, 24.0, safe, 0, "확정된 센서 및 비전 위험 없음"),
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
