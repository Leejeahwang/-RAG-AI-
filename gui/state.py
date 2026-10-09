"""
gui/state.py
============
EDGE SAVER 관제 대시보드의 thread-safe 공유 상태.

대시보드는 표시 전용이다. 판단(위험도, 경보, 대피 방송)은 Pi 의 main.py 가 하고,
이 모듈은 MQTT 로 받은 결과를 구역별로 보관한다.

    - UI 상수 (refresh 주기, gauge 색 등)
    - RuntimeState 싱글톤 (RLock 보호)
        · 구역별 수신 상태 (status / event / frame / online)
        · 브로커 연결 상태
        · 관제사 질의(RAG) 답변, STT, 로그, 테마
    - escape_html / detect_lang 헬퍼
"""

from __future__ import annotations

import html
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from gui.mqtt_settings import STALE_SECONDS
from gui.protocol import (
    EVENT_ALARM_END,
    EVENT_ALARM_START,
    EVENT_GUIDANCE,
    EventMsg,
    OnlineMsg,
    Sensors,
    StatusMsg,
    provider_label,
)


# ════════════════════════════════════════════════════════════════
#  UI 상수
# ════════════════════════════════════════════════════════════════

# 경보 단계 (main.py 와 동일: LV4 이상이면 Pi 가 경보·대피 방송 시작)
ALERT_THRESHOLD = 4

# 로그 / 트렌드 / 이력 버퍼
LOG_MAX = 120
TREND_WINDOW = 120   # 약 2분 (@1s status)
EVENT_MAX = 50

# Fragment 갱신 주기 (초)
REFRESH_CAMERA = 0.5
REFRESH_SENSORS = 1.0
REFRESH_GAUGE = 1.0
REFRESH_AI = 1.0
REFRESH_TREND = 1.0
REFRESH_LOG = 2.0
REFRESH_STATUS = 1.0

# Worker 주기
STT_IDLE_WAIT = 0.3

# 마지막 status 수신 후 이 시간이 지나면 "신호 지연"
STALE_THRESHOLD = STALE_SECONDS
# 마지막 frame 수신 후 이 시간이 지나면 카메라 영상 끊김
FRAME_STALE_THRESHOLD = 3.0

# LV 0~5
GAUGE_COLORS = ["#22c55e", "#84cc16", "#facc15", "#f97316", "#ef4444", "#7f1d1d"]

# LLM 우선순위 (관제사 질의만 남음)
LLM_PRIORITY_QUERY = 10


# ════════════════════════════════════════════════════════════════
#  Snapshots
# ════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TrendPoint:
    ts: float
    sensors: Sensors


@dataclass(frozen=True)
class STTMessage:
    text: str
    lang: str
    ts: float


@dataclass(frozen=True)
class ZoneView:
    """UI 가 한 번에 읽어 가는 구역 스냅샷 (불변)."""
    zone: str
    status: Optional[StatusMsg]
    status_rx: float               # 마지막 status 수신 시각 (관제 PC 시계)
    online: Optional[bool]         # online 토픽 값. None = 아직 모름
    online_rx: float
    frame: Optional[bytes]
    frame_rx: float
    events: Tuple[EventMsg, ...]
    alarm_since: float             # 경보 시작 수신 시각, 경보 아니면 0

    @property
    def last_seen(self) -> float:
        return max(self.status_rx, self.online_rx, self.frame_rx)

    @property
    def stale(self) -> bool:
        return self.status is None or (time.time() - self.status_rx) > STALE_THRESHOLD

    @property
    def connected(self) -> bool:
        """Pi 가 살아 있고 최근 status 를 받았는가."""
        return self.online is not False and not self.stale

    @property
    def frame_live(self) -> bool:
        return self.frame is not None and (time.time() - self.frame_rx) <= FRAME_STALE_THRESHOLD

    @property
    def level(self) -> int:
        return self.status.risk.level if self.status and self.connected else 0


@dataclass
class _ZoneData:
    status: Optional[StatusMsg] = None
    status_rx: float = 0.0
    online: Optional[bool] = None
    online_rx: float = 0.0
    frame: Optional[bytes] = None
    frame_rx: float = 0.0
    events: Deque[EventMsg] = field(default_factory=lambda: deque(maxlen=EVENT_MAX))
    seen_events: Deque[Tuple[int, float]] = field(default_factory=lambda: deque(maxlen=EVENT_MAX))
    trend: Deque[TrendPoint] = field(default_factory=lambda: deque(maxlen=TREND_WINDOW))
    alarm_since: float = 0.0

    def view(self, zone: str) -> ZoneView:
        return ZoneView(
            zone=zone, status=self.status, status_rx=self.status_rx,
            online=self.online, online_rx=self.online_rx,
            frame=self.frame, frame_rx=self.frame_rx,
            events=tuple(self.events), alarm_since=self.alarm_since,
        )


# ════════════════════════════════════════════════════════════════
#  RuntimeState
# ════════════════════════════════════════════════════════════════

class RuntimeState:
    """프로세스 전역 단일 인스턴스. 모든 접근은 단일 RLock 보호.

    선택한 구역(active zone)은 브라우저 탭마다 다르므로 여기 두지 않고
    Streamlit session_state 에 둔다 (components.active_zone)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()

        self._zones: Dict[str, _ZoneData] = {}
        self._broker_connected = False
        self._broker_error = ""
        self._broker_target = ""

        self._logs: deque = deque(maxlen=LOG_MAX)

        # 관제사 질의 (관제 PC 자체 RAG)
        self._qa_ready = False
        self._last_answer = ""
        self._last_provider = ""
        self._last_generated_at = 0.0
        self._is_generating = False

        self._stt_enabled = False
        self._stt_queue: "queue.Queue[STTMessage]" = queue.Queue(maxsize=16)
        self._stt_dropped = False

        self._theme = "dark"
        self._system_offline = False

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

    # ── 브로커 연결 ──
    def set_broker(self, connected: bool, error: str = "", target: Optional[str] = None) -> None:
        with self._lock:
            self._broker_connected = connected
            self._broker_error = "" if connected else error
            if target is not None:
                self._broker_target = target

    def get_broker(self) -> Tuple[bool, str, str]:
        with self._lock:
            return self._broker_connected, self._broker_error, self._broker_target

    # ── MQTT 수신 반영 ──
    def _zone(self, zone: str) -> _ZoneData:
        data = self._zones.get(zone)
        if data is None:
            data = self._zones[zone] = _ZoneData()
        return data

    def apply_status(self, msg: StatusMsg, rx: Optional[float] = None) -> None:
        rx = time.time() if rx is None else rx
        with self._lock:
            z = self._zone(msg.zone)
            prev = z.status
            z.status, z.status_rx = msg, rx
            if z.online is None:
                z.online = True
            z.trend.append(TrendPoint(rx, msg.sensors))
            # 대시보드가 경보 도중에 켜진 경우: event 를 놓쳤어도 status 로 경보 시작을 잡는다
            if msg.alarm and not z.alarm_since:
                z.alarm_since = rx
            elif not msg.alarm:
                z.alarm_since = 0.0
            if prev is None:
                self._log(f"📡 [{msg.zone}구역] 상태 수신 시작 ({msg.sensor_mode})")

    def apply_event(self, msg: EventMsg, rx: Optional[float] = None) -> bool:
        """새 이벤트면 True. QoS1 중복 수신은 무시한다."""
        rx = time.time() if rx is None else rx
        with self._lock:
            z = self._zone(msg.zone)
            key = (msg.seq, msg.ts)
            if key in z.seen_events:
                return False
            z.seen_events.append(key)
            z.events.append(msg)
            if msg.type == EVENT_ALARM_START:
                z.alarm_since = z.alarm_since or rx
                self._log(f"🚨 [{msg.zone}구역] 경보 시작 LV{msg.level} — {msg.details}")
            elif msg.type == EVENT_ALARM_END:
                z.alarm_since = 0.0
                self._log(f"✅ [{msg.zone}구역] 정상 복귀, 경보 종료")
            elif msg.type == EVENT_GUIDANCE:
                kind = "비상 지침" if msg.emergency else "현장 질의 답변"
                reason = f" (전환 이유: {msg.fallback_reason})" if msg.fallback_reason else ""
                self._log(f"🤖 [{msg.zone}구역] {kind} · {provider_label(msg.provider)}{reason}")
            return True

    def apply_frame(self, zone: str, jpeg: bytes, rx: Optional[float] = None) -> None:
        with self._lock:
            z = self._zone(zone)
            z.frame, z.frame_rx = jpeg, time.time() if rx is None else rx

    def apply_online(self, msg: OnlineMsg, rx: Optional[float] = None) -> None:
        rx = time.time() if rx is None else rx
        with self._lock:
            z = self._zone(msg.zone)
            if z.online is not msg.online:
                self._log(f"{'🟢' if msg.online else '🔴'} [{msg.zone}구역] Pi {'온라인' if msg.online else '오프라인'}")
            z.online, z.online_rx = msg.online, rx

    # ── 구역 조회 ──
    def zone_ids(self) -> List[str]:
        with self._lock:
            return sorted(self._zones)

    def get_zone(self, zone: Optional[str]) -> Optional[ZoneView]:
        with self._lock:
            z = self._zones.get(zone) if zone else None
            return z.view(zone) if z else None

    def all_zones(self) -> List[ZoneView]:
        with self._lock:
            return [self._zones[k].view(k) for k in sorted(self._zones)]

    def get_trend(self, zone: Optional[str]) -> List[TrendPoint]:
        with self._lock:
            z = self._zones.get(zone) if zone else None
            return list(z.trend) if z else []

    def max_level(self) -> int:
        return max((v.level for v in self.all_zones()), default=0)

    # ── logs ──
    def _log(self, msg: str) -> None:
        self._logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def add_log(self, msg: str) -> None:
        with self._lock:
            self._log(msg)

    def snapshot_logs(self) -> List[str]:
        with self._lock:
            return list(self._logs)

    # ── 관제사 질의 (관제 PC RAG) ──
    def set_qa_ready(self, flag: bool) -> None:
        with self._lock:
            self._qa_ready = flag

    def is_qa_ready(self) -> bool:
        with self._lock:
            return self._qa_ready

    def set_last_answer(self, text: str, provider: str = "") -> None:
        with self._lock:
            self._last_answer = text
            self._last_provider = provider
            self._last_generated_at = time.time()

    def get_last_answer(self) -> Tuple[str, str, float]:
        with self._lock:
            return self._last_answer, self._last_provider, self._last_generated_at

    def set_generating(self, flag: bool) -> None:
        with self._lock:
            self._is_generating = flag

    def is_generating(self) -> bool:
        with self._lock:
            return self._is_generating

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

    def set_stt_dropped(self) -> None:
        with self._lock:
            self._stt_dropped = True

    def pop_stt_dropped(self) -> bool:
        with self._lock:
            val = self._stt_dropped
            self._stt_dropped = False
            return val

    # ── theme ──
    def set_theme(self, theme: str) -> None:
        with self._lock:
            self._theme = "light" if theme == "light" else "dark"

    def get_theme(self) -> str:
        with self._lock:
            return self._theme


# 프로세스 전역 싱글톤
RUNTIME = RuntimeState()


# ════════════════════════════════════════════════════════════════
#  헬퍼
# ════════════════════════════════════════════════════════════════

def escape_html(text) -> str:
    """XSS 방지 — LLM/STT/MQTT 문자열을 unsafe_allow_html에 넣기 전 호출."""
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
