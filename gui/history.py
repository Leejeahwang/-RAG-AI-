"""
gui/history.py
==============
수신한 event 를 "경보 1건" 단위로 묶는다 (경보 이력 패널용).

    alarm_start ─ guidance(비상) ─ guidance ... ─ alarm_end   →  Incident 1건
    warning (Level 2 비전 경고 방송)                           →  Incident 1건 (kind="warning")

- 시각은 모두 Pi 가 보낸 ts 를 쓴다. 시작·종료가 같은 시계라 지속 시간이 정확하다.
- 대시보드가 경보 도중에 켜져 alarm_start 를 못 받은 경우, status 의 alarm 플래그로
  "진행 중 · 시작 기록 없음" 경보를 만든다.
- 현장 일반 질문 답변(guidance, emergency=False)은 경보에 넣지 않는다.

화면 코드와 분리해 두어 tests/test_history.py 에서 바로 검증한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from gui.protocol import EVENT_ALARM_END, EVENT_ALARM_START, EVENT_GUIDANCE, EVENT_WARNING, EventMsg


@dataclass
class Incident:
    start_ts: Optional[float]          # None = 시작 기록 없음 (대시보드가 도중에 켜짐)
    end_ts: Optional[float] = None     # None = 진행 중
    level: int = 0
    details: str = ""
    guidances: List[EventMsg] = field(default_factory=list)
    end_unknown: bool = False          # 종료 event 를 놓쳤지만 status 는 이미 정상
    local_since: Optional[float] = None  # 진행 중일 때 관제 PC 시계 기준 시작 시각
    kind: str = "alarm"                # alarm (Level 4·5 경보) | warning (Level 2 비전 경고)
    fire_zone: str = ""                # 화재 구역 (다른 Pi 의 경보를 받은 경우 이 Pi 구역과 다름)

    @property
    def ongoing(self) -> bool:
        return self.end_ts is None and not self.end_unknown

    def duration(self, now: float) -> Optional[float]:
        """초. 끝난 경보는 Pi 시각끼리, 진행 중 경보는 관제 PC 시각끼리 계산한다
        (두 기기 시계 차이가 섞이지 않게). 계산할 수 없으면 None."""
        if self.end_ts is not None:
            return None if self.start_ts is None else max(0.0, self.end_ts - self.start_ts)
        if self.ongoing and self.local_since:
            return max(0.0, now - self.local_since)
        return None

    @property
    def sort_key(self) -> float:
        times = [t for t in (self.start_ts, self.end_ts) if t is not None]
        times += [g.ts for g in self.guidances]
        return max(times, default=0.0)


def group_incidents(
    events: Iterable[EventMsg],
    alarm_active: bool = False,
    alarm_since: Optional[float] = None,
    limit: int = 10,
) -> List[Incident]:
    """event 목록(수신 순서) → 경보 목록 (최신 경보가 앞).

    alarm_active / alarm_since: 현재 status 의 경보 여부와 그 시작 시각(관제 PC 기준).
    event 로 열린 경보가 없는데 경보 중이면 "시작 기록 없음" 경보를 하나 만든다."""
    incidents: List[Incident] = []
    current: Optional[Incident] = None

    for ev in sorted(events, key=lambda e: (e.ts, e.seq)):
        if ev.type == EVENT_ALARM_START:
            if current is not None and current.ongoing:
                # 종료 없이 새 경보: 이전 경보는 새 경보 시작 시각에 끝난 것으로 본다
                current.end_ts = ev.ts
            current = Incident(start_ts=ev.ts, level=ev.level, details=ev.details, fire_zone=ev.fire_zone)
            if ev.text:
                # 첫 고정 안내도 지침 목록 맨 앞에 보여 준다
                current.guidances.append(ev)
            incidents.append(current)
        elif ev.type == EVENT_GUIDANCE and ev.emergency:
            if current is None or not current.ongoing:
                current = Incident(start_ts=None)
                incidents.append(current)
            current.guidances.append(ev)
        elif ev.type == EVENT_ALARM_END:
            if current is None or not current.ongoing:
                current = Incident(start_ts=None)
                incidents.append(current)
            current.end_ts = ev.ts
        elif ev.type == EVENT_WARNING:
            # 경보(current)와 별개인 한 번의 경고 방송. 진행 중 경보를 닫지 않는다.
            incidents.append(Incident(start_ts=ev.ts, end_ts=ev.ts, level=ev.level, details=ev.details,
                                      guidances=[ev], kind="warning", fire_zone=ev.fire_zone))

    if alarm_active:
        if current is None or not current.ongoing:
            current = Incident(start_ts=None)
            incidents.append(current)
        current.local_since = alarm_since or None
    elif current is not None and current.ongoing:
        # status 는 정상인데 종료 event 를 놓친 경우: 진행 중으로 남겨 두지 않는다
        current.end_unknown = True

    # 진행 중 경보가 맨 앞, 나머지는 최근 순
    incidents.sort(key=lambda i: (i.ongoing, i.sort_key), reverse=True)
    return incidents[:limit]
