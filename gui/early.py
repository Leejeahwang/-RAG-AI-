"""
gui/early.py
============
Level 2 조기 알림: "비전 감지 → 센서 반응" 선행 시간 측정 (구역별).

    대기(idle) ── 비전이 먼저 감지, 센서는 임계값 아래 ──▶ 센서 대기(waiting)
    센서 대기 ── 센서 임계값 초과 ──▶ 반응(reacted)  · 선행 시간 = 센서 시각 − 비전 시각
    센서 대기 ── 비전 감지가 10초 넘게 사라짐 ──▶ 대기  · "센서 반응 없이 종료"
    반응 ── 비전·센서·경보가 모두 5초 넘게 정상 ──▶ 대기 (다음 측정 준비)

- 선행 시간은 Pi 가 보낸 ts 끼리 뺀다 (같은 시계라 정확).
- 진행 중 "○초 경과" 표시는 관제 PC 수신 시각끼리 계산한다 (두 기기 시계 차이를 섞지 않음).
- 센서 임계값은 config.SENSOR_THRESHOLDS (sensors/fusion.py 와 같은 기준: 값 > 임계값).

화면 코드와 분리해 두어 tests/test_early.py 에서 바로 검증한다.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Mapping, Optional, Tuple

from gui.protocol import StatusMsg

try:
    import config
    THRESHOLDS = dict(config.SENSOR_THRESHOLDS)
except Exception:  # 관제 PC 에서 config 를 못 읽어도 동작
    THRESHOLDS = {"smoke_mq2": 300, "gas_mq135": 400, "temperature_high": 60}

CLEAR_SECONDS = 10.0     # 센서 대기 중 비전 감지가 이 시간 동안 없으면 "반응 없이 종료"
REARM_SECONDS = 5.0      # 측정이 끝난 뒤 이 시간 동안 모두 정상이면 다음 측정 준비
RESULT_MAX = 10

IDLE, WAITING, REACTED = "idle", "waiting", "reacted"


def vision_first(msg: StatusMsg) -> bool:
    """비전이 연기·불꽃을 잡은 상태 (사진 오탐 차단은 제외)."""
    v = msg.vision
    if v.photo_blocked or v.camera_offline:
        return False
    return bool(msg.risk.early or v.real_smoke or v.fire_detected)


def sensors_over(msg: StatusMsg, thresholds: Mapping[str, float] = THRESHOLDS) -> Tuple[str, ...]:
    """임계값을 넘은 센서 이름들 (fusion.py 와 같은 '초과' 기준)."""
    s = msg.sensors
    names = []
    if s.smoke > thresholds["smoke_mq2"]:
        names.append("연기")
    if s.gas > thresholds["gas_mq135"]:
        names.append("가스")
    if s.temperature > thresholds["temperature_high"]:
        names.append("온도")
    return tuple(names)


@dataclass(frozen=True)
class EarlyResult:
    vision_ts: float                 # Pi 시각: 비전이 먼저 감지
    sensor_ts: Optional[float]       # Pi 시각: 센서 반응 (None = 반응 없이 종료)
    sensors: Tuple[str, ...] = ()    # 반응한 센서

    @property
    def lead(self) -> Optional[float]:
        return None if self.sensor_ts is None else max(0.0, self.sensor_ts - self.vision_ts)


@dataclass(frozen=True)
class EarlyView:
    """UI 가 읽어 가는 스냅샷."""
    phase: str = IDLE
    since_rx: float = 0.0            # 관제 PC 시각: 센서 대기 시작
    results: Tuple[EarlyResult, ...] = ()

    @property
    def waiting(self) -> bool:
        return self.phase == WAITING

    @property
    def last(self) -> Optional[EarlyResult]:
        return self.results[-1] if self.results else None


class EarlyTracker:
    def __init__(self) -> None:
        self.phase = IDLE
        self._vision_ts = 0.0
        self._since_rx = 0.0
        self._last_active_rx = 0.0
        self.results: Deque[EarlyResult] = deque(maxlen=RESULT_MAX)

    def view(self) -> EarlyView:
        return EarlyView(self.phase, self._since_rx if self.phase == WAITING else 0.0, tuple(self.results))

    def update(self, msg: StatusMsg, rx: float,
               thresholds: Mapping[str, float] = THRESHOLDS) -> Optional[str]:
        """status 1개 반영. 로그로 남길 문장이 생기면 돌려준다."""
        early = vision_first(msg)
        over = sensors_over(msg, thresholds)

        if self.phase == IDLE:
            if early and not over:
                self.phase = WAITING
                self._vision_ts, self._since_rx, self._last_active_rx = msg.ts, rx, rx
                return "조기 감지 — 비전이 먼저 포착, 센서 반응 대기"
            return None

        if self.phase == WAITING:
            if over:
                result = EarlyResult(self._vision_ts, msg.ts, over)
                self.results.append(result)
                self.phase, self._last_active_rx = REACTED, rx
                return f"센서 반응({', '.join(over)}) — 비전이 {result.lead:.1f}초 먼저 감지"
            if early:
                self._last_active_rx = rx
            elif rx - self._last_active_rx > CLEAR_SECONDS:
                self.results.append(EarlyResult(self._vision_ts, None))
                self.phase = IDLE
                return "조기 감지 해제 — 센서 반응 없이 종료"
            return None

        # REACTED: 모두 정상으로 충분히 돌아오면 다음 측정 준비
        if early or over or msg.alarm:
            self._last_active_rx = rx
        elif rx - self._last_active_rx > REARM_SECONDS:
            self.phase = IDLE
        return None
