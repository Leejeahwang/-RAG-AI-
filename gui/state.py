"""
gui/state.py
============
EDGE SAVER 대시보드의 thread-safe 공유 상태.

이 모듈 한 곳에 모은 것:
    - UI 상수 (refresh 주기, gauge 색, 임계값 등)
    - RuntimeState 싱글톤 (RLock 보호)
    - escape_html 헬퍼
"""

from __future__ import annotations

import html
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


# ════════════════════════════════════════════════════════════════
#  UI 상수
# ════════════════════════════════════════════════════════════════

# 알람 트리거 임계값 (이 이상이면 RAG 자동 생성)
ALERT_THRESHOLD = 4

# 로그 / 트렌드 버퍼
LOG_MAX = 80
TREND_WINDOW = 120  # 약 2분 (@1s)

# Fragment 갱신 주기 (초)
REFRESH_CAMERA = 1.0
REFRESH_SENSORS = 1.0
REFRESH_GAUGE = 1.0
REFRESH_AI = 1.0
REFRESH_TREND = 1.0
REFRESH_LOG = 2.0
REFRESH_STATUS = 2.0

# Worker 주기
SENSOR_INTERVAL = 1.0
FIRE_INTERVAL = 2.0
STT_IDLE_WAIT = 0.3

# UI
CAM_WIDTH = 720
STALE_THRESHOLD = 5.0

# LV 0~5
GAUGE_COLORS = ["#22c55e", "#84cc16", "#facc15", "#f97316", "#ef4444", "#7f1d1d"]

# LLM 우선순위
LLM_PRIORITY_EMERGENCY = 0
LLM_PRIORITY_QUERY = 10

# 라즈베리파이 여부 자동 감지
def _is_raspberry_pi() -> bool:
    try:
        with open("/proc/cpuinfo", "r") as f:
            return "Raspberry Pi" in f.read()
    except OSError:
        return False

_ON_PI = _is_raspberry_pi()
# Pi: 실제 GPIO 읽기 / PC + MQTT_MODE=1: MQTT 수신 / PC 기본: 시뮬레이션
SIMULATE = not _ON_PI and os.environ.get("MQTT_MODE", "0") != "1"
MQTT_MODE = not _ON_PI and os.environ.get("MQTT_MODE", "0") == "1"


# ════════════════════════════════════════════════════════════════
#  Dataclass snapshots
# ════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SensorSnapshot:
    smoke: int
    gas: int
    temperature: float
    humidity: float
    ts: float


@dataclass(frozen=True)
class FireSnapshot:
    detected: bool
    confidence: float
    description: str
    ts: float


@dataclass(frozen=True)
class RiskSnapshot:
    level: int
    label: str
    details: str
    ts: float


@dataclass(frozen=True)
class STTMessage:
    text: str
    lang: str
    ts: float


_NULL_FIRE = FireSnapshot(False, 0.0, "대기 중", 0.0)
_NULL_RISK = RiskSnapshot(0, "정상", "대기 중", 0.0)


# ════════════════════════════════════════════════════════════════
#  RuntimeState
# ════════════════════════════════════════════════════════════════

class RuntimeState:
    """프로세스 전역 단일 인스턴스. 모든 접근은 단일 RLock 보호."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()

        self._sensors: Optional[SensorSnapshot] = None
        self._fire: FireSnapshot = _NULL_FIRE
        self._risk: RiskSnapshot = _NULL_RISK
        self._frame: Optional[np.ndarray] = None
        self._trend: deque = deque(maxlen=TREND_WINDOW)
        self._logs: deque = deque(maxlen=LOG_MAX)

        self._last_answer: str = ""
        self._is_generating: bool = False
        self._first_alert: bool = True

        self._stt_enabled: bool = False
        self._stt_queue: "queue.Queue[STTMessage]" = queue.Queue(maxsize=16)

        self._theme: str = "dark"
        self._zone: str = "A구역 센서노드_01"
        self._system_offline: bool = False

        # 멀티존 (MQTT 관제 모드)
        self._zones_sensors: Dict[str, SensorSnapshot] = {}
        self._zones_fire: Dict[str, FireSnapshot] = {}
        self._zones_risk: Dict[str, RiskSnapshot] = {}
        self._zones_last_seen: Dict[str, float] = {}
        self._zones_alert_active: Dict[str, bool] = {}   # 구역별 알림 CAS
        self._active_zone: Optional[str] = None

    # ── stop / shutdown ──
    def stop_event(self) -> threading.Event:
        return self._stop_event

    def request_shutdown(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._system_offline = True

    def is_offline(self) -> bool:
        with self._lock:
            return self._system_offline

    # ── sensors ──
    def set_sensors(self, snap: SensorSnapshot) -> None:
        with self._lock:
            self._sensors = snap
            self._trend.append(snap)

    def get_sensors(self) -> Optional[SensorSnapshot]:
        with self._lock:
            if MQTT_MODE and self._active_zone:
                return self._zones_sensors.get(self._active_zone)
            return self._sensors

    def snapshot_trend(self) -> List[SensorSnapshot]:
        with self._lock:
            return list(self._trend)

    # ── fire ──
    def set_fire(self, snap: FireSnapshot) -> None:
        with self._lock:
            self._fire = snap

    def get_fire(self) -> FireSnapshot:
        with self._lock:
            if MQTT_MODE and self._active_zone:
                return self._zones_fire.get(self._active_zone, _NULL_FIRE)
            return self._fire

    # ── risk ──
    def set_risk(self, snap: RiskSnapshot) -> None:
        with self._lock:
            self._risk = snap

    def get_risk(self) -> RiskSnapshot:
        with self._lock:
            if MQTT_MODE and self._active_zone:
                return self._zones_risk.get(self._active_zone, _NULL_RISK)
            return self._risk

    # ── 멀티존 (MQTT 관제 모드) ──
    def set_zone_sensors(self, zone: str, snap: SensorSnapshot) -> None:
        with self._lock:
            self._zones_sensors[zone] = snap
            self._zones_last_seen[zone] = snap.ts
            if zone == self._active_zone:
                self._trend.append(snap)

    def set_zone_fire(self, zone: str, snap: FireSnapshot) -> None:
        with self._lock:
            self._zones_fire[zone] = snap

    def set_zone_risk(self, zone: str, snap: RiskSnapshot) -> None:
        with self._lock:
            self._zones_risk[zone] = snap

    def get_all_zones(self) -> Dict[str, SensorSnapshot]:
        with self._lock:
            return dict(self._zones_sensors)

    def get_zone_fire(self, zone: str) -> FireSnapshot:
        with self._lock:
            return self._zones_fire.get(zone, _NULL_FIRE)

    def get_zone_risk(self, zone: str) -> RiskSnapshot:
        with self._lock:
            return self._zones_risk.get(zone, _NULL_RISK)

    def get_zone_last_seen(self, zone: str) -> float:
        with self._lock:
            return self._zones_last_seen.get(zone, 0.0)

    def get_active_zone(self) -> Optional[str]:
        with self._lock:
            return self._active_zone

    def set_active_zone(self, zone: Optional[str]) -> None:
        with self._lock:
            if zone != self._active_zone:
                self._trend.clear()
            self._active_zone = zone

    # ── 구역별 알림 CAS (백그라운드 디스패처용) ──
    def try_claim_zone_alert(self, zone: str) -> bool:
        with self._lock:
            if not self._zones_alert_active.get(zone, False):
                self._zones_alert_active[zone] = True
                return True
            return False

    def reset_zone_alert(self, zone: str) -> None:
        with self._lock:
            self._zones_alert_active[zone] = False

    # ── frame ──
    def set_frame(self, frame: Optional[np.ndarray]) -> None:
        if frame is None:
            return
        copy = frame.copy()
        with self._lock:
            self._frame = copy

    def get_frame_copy(self) -> Optional[np.ndarray]:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    # ── logs ──
    def add_log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        with self._lock:
            self._logs.append(line)

    def snapshot_logs(self) -> List[str]:
        with self._lock:
            return list(self._logs)

    # ── ai ──
    def set_last_answer(self, text: str) -> None:
        with self._lock:
            self._last_answer = text

    def get_last_answer(self) -> str:
        with self._lock:
            return self._last_answer

    def set_generating(self, flag: bool) -> None:
        with self._lock:
            self._is_generating = flag

    def is_generating(self) -> bool:
        with self._lock:
            return self._is_generating

    # ── alert claim (CAS) ──
    def try_claim_alert(self) -> bool:
        with self._lock:
            if self._first_alert:
                self._first_alert = False
                return True
            return False

    def reset_alert(self) -> None:
        with self._lock:
            self._first_alert = True

    # ── stt ──
    def set_stt_enabled(self, flag: bool) -> None:
        with self._lock:
            self._stt_enabled = flag

    def is_stt_enabled(self) -> bool:
        with self._lock:
            return self._stt_enabled

    def push_stt(self, msg: STTMessage) -> bool:
        try:
            self._stt_queue.put_nowait(msg)
            return True
        except queue.Full:
            return False

    def pop_stt(self) -> Optional[STTMessage]:
        try:
            return self._stt_queue.get_nowait()
        except queue.Empty:
            return None

    # ── theme / zone ──
    def set_theme(self, theme: str) -> None:
        with self._lock:
            self._theme = "light" if theme == "light" else "dark"

    def get_theme(self) -> str:
        with self._lock:
            return self._theme

    def get_zone(self) -> str:
        with self._lock:
            if MQTT_MODE and self._active_zone:
                return self._active_zone
            return self._zone


# 프로세스 전역 싱글톤
RUNTIME = RuntimeState()


# ════════════════════════════════════════════════════════════════
#  헬퍼
# ════════════════════════════════════════════════════════════════

def escape_html(text) -> str:
    """XSS 방지 — LLM/STT 출력을 unsafe_allow_html에 넣기 전 호출."""
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


def detect_lang(text: str) -> str:
    """간단한 언어 감지 (한/일/중/영, 기본 한국어)."""
    import re
    if not text:
        return "ko"
    if re.search(r"[가-힣]", text):
        return "ko"
    if re.search(r"[ぁ-んァ-ヶ]", text):
        return "ja"
    if re.search(r"[一-鿿]", text):
        return "zh"
    if re.search(r"[a-zA-Z]", text):
        return "en"
    return "ko"
