"""
gui/protocol.py
===============
Pi ↔ 관제 대시보드 MQTT 메시지 형식. 필드 설명은 gui/PROTOCOL.md 참고.

- build_* : Pi(edge_publisher)가 dict → JSON bytes 를 만든다.
- parse_* : 대시보드가 bytes → dataclass 로 읽는다.
            필드가 빠져 있거나 타입이 달라도 기본값으로 채우고,
            JSON 자체가 깨졌을 때만 ValueError 를 낸다.

frame 토픽은 JSON이 아니라 JPEG 바이트 그대로 보낸다.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from gui.mqtt_settings import SCHEMA_VERSION

# 위험도 0~5 (sensors/fusion.py, config.RISK_LEVELS 와 동일)
LEVEL_LABELS = {0: "정상", 1: "주의", 2: "경고", 3: "위험", 4: "긴급", 5: "재난"}
MAX_LEVEL = 5

# rag/provider.py GuidanceResult.provider 값 → 화면 표시 이름
PROVIDER_LABELS = {
    "gemini": "Gemini",
    "ollama": "로컬 Qwen",
    "fixed": "고정 안내",
}

# vision/smoke_motion.py 가 실제 사진으로 판정했을 때만 쓰는 상태값
PHOTO_BLOCK_STATUSES = frozenset({"STATIC_PHOTO_BLOCKED", "HANDHELD_PHOTO_BLOCKED"})
CAMERA_OFFLINE_STATUS = "CAMERA_OFFLINE"

EVENT_ALARM_START = "alarm_start"
EVENT_ALARM_END = "alarm_end"
EVENT_GUIDANCE = "guidance"
EVENT_TYPES = (EVENT_ALARM_START, EVENT_ALARM_END, EVENT_GUIDANCE)

_TEXT_LIMIT = 2000


def provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, provider or "-")


def clamp_level(value: Any) -> int:
    return max(0, min(_int(value), MAX_LEVEL))


# ════════════════════════════════════════════════════════════════
#  타입 보정 헬퍼
# ════════════════════════════════════════════════════════════════

def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)[:_TEXT_LIMIT]


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _encode(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _decode(raw: bytes | str) -> Mapping[str, Any]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"JSON 형식 오류: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ValueError("JSON 객체가 아님")
    return data


# ════════════════════════════════════════════════════════════════
#  메시지 dataclass (대시보드 쪽)
# ════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Sensors:
    temperature: float = 0.0
    humidity: float = 0.0
    gas: int = 0      # MQ-135 ADC 원시값 0~1023
    smoke: int = 0    # MQ-2 ADC 원시값 0~1023


@dataclass(frozen=True)
class Risk:
    level: int = 0           # 화면에 쓰는 위험도 (경보 중에는 경보 시작 단계 이상 유지)
    fused_level: int = 0     # 이번 주기 fusion 계산값
    label: str = "정상"
    details: str = ""
    early: bool = False      # fusion.is_early_detection


@dataclass(frozen=True)
class Vision:
    status: str = ""
    fire_detected: bool = False
    real_smoke: bool = False
    static_photo: bool = False
    confidence: float = 0.0
    description: str = ""

    @property
    def camera_offline(self) -> bool:
        return self.status == CAMERA_OFFLINE_STATUS

    @property
    def photo_blocked(self) -> bool:
        return self.status in PHOTO_BLOCK_STATUSES


@dataclass(frozen=True)
class AIState:
    text: str = ""
    provider: str = ""
    fallback_reason: str = ""
    ts: float = 0.0


@dataclass(frozen=True)
class StatusMsg:
    zone: str
    ts: float
    sensor_mode: str = "demo"
    sensors: Sensors = field(default_factory=Sensors)
    risk: Risk = field(default_factory=Risk)
    vision: Vision = field(default_factory=Vision)
    alarm: bool = False
    ai: AIState = field(default_factory=AIState)
    version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class EventMsg:
    zone: str
    ts: float
    seq: int
    type: str
    level: int = 0
    details: str = ""
    text: str = ""
    provider: str = ""
    fallback_reason: str = ""
    emergency: bool = False


@dataclass(frozen=True)
class OnlineMsg:
    zone: str
    online: bool
    ts: float


# ════════════════════════════════════════════════════════════════
#  build (Pi 쪽)
# ════════════════════════════════════════════════════════════════

def build_status(
    zone: str,
    *,
    sensor_mode: str,
    temp: Mapping[str, Any],
    gas: Any,
    smoke: Any,
    risk: Mapping[str, Any],
    level: int,
    analysis: Mapping[str, Any],
    alarm: bool,
    ai: AIState,
    ts: float | None = None,
) -> bytes:
    """main.py _monitor_once 의 지역 변수를 그대로 받아 status JSON 을 만든다."""
    analysis = _dict(analysis)
    shown = clamp_level(level)
    return _encode({
        "v": SCHEMA_VERSION,
        "zone": zone,
        "ts": time.time() if ts is None else ts,
        "sensor_mode": _str(sensor_mode, "demo"),
        "sensors": {
            "temperature": _float(_dict(temp).get("temperature")),
            "humidity": _float(_dict(temp).get("humidity")),
            "gas": _int(gas),
            "smoke": _int(smoke),
        },
        "risk": {
            "level": shown,
            "fused_level": clamp_level(_dict(risk).get("level")),
            "label": LEVEL_LABELS[shown],
            "details": _str(_dict(risk).get("details")),
            "early": _bool(_dict(risk).get("is_early_detection")),
        },
        "vision": {
            "status": _str(analysis.get("status")),
            "fire_detected": _bool(analysis.get("fire_detected")),
            "real_smoke": _bool(analysis.get("is_real_smoke")),
            "static_photo": _bool(analysis.get("is_static_photo")),
            "confidence": round(_float(analysis.get("confidence")), 3),
            "description": _str(analysis.get("description")),
        },
        "alarm": bool(alarm),
        "ai": {
            "text": _str(ai.text),
            "provider": _str(ai.provider),
            "fallback_reason": _str(ai.fallback_reason),
            "ts": ai.ts,
        },
    })


def build_event(zone: str, seq: int, event_type: str, ts: float | None = None, **fields: Any) -> bytes:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"알 수 없는 event type: {event_type}")
    payload = {
        "v": SCHEMA_VERSION,
        "zone": zone,
        "ts": time.time() if ts is None else ts,
        "seq": int(seq),
        "type": event_type,
    }
    for key in ("level", "details", "text", "provider", "fallback_reason", "emergency"):
        if key in fields and fields[key] is not None:
            payload[key] = fields[key]
    return _encode(payload)


def build_online(zone: str, online: bool, ts: float | None = None) -> bytes:
    return _encode({
        "v": SCHEMA_VERSION,
        "zone": zone,
        "online": bool(online),
        "ts": time.time() if ts is None else ts,
    })


# ════════════════════════════════════════════════════════════════
#  parse (대시보드 쪽)
# ════════════════════════════════════════════════════════════════

def parse_status(raw: bytes | str, zone: str) -> StatusMsg:
    d = _decode(raw)
    s, r, v, a = (_dict(d.get(k)) for k in ("sensors", "risk", "vision", "ai"))
    level = clamp_level(r.get("level"))
    return StatusMsg(
        zone=zone,
        ts=_float(d.get("ts"), time.time()),
        sensor_mode=_str(d.get("sensor_mode"), "demo").lower(),
        sensors=Sensors(
            temperature=_float(s.get("temperature")),
            humidity=_float(s.get("humidity")),
            gas=_int(s.get("gas")),
            smoke=_int(s.get("smoke")),
        ),
        risk=Risk(
            level=level,
            fused_level=clamp_level(r.get("fused_level", level)),
            label=_str(r.get("label")) or LEVEL_LABELS[level],
            details=_str(r.get("details")),
            early=_bool(r.get("early")),
        ),
        vision=Vision(
            status=_str(v.get("status")),
            fire_detected=_bool(v.get("fire_detected")),
            real_smoke=_bool(v.get("real_smoke")),
            static_photo=_bool(v.get("static_photo")),
            confidence=_float(v.get("confidence")),
            description=_str(v.get("description")),
        ),
        alarm=_bool(d.get("alarm")),
        ai=AIState(
            text=_str(a.get("text")),
            provider=_str(a.get("provider")),
            fallback_reason=_str(a.get("fallback_reason")),
            ts=_float(a.get("ts")),
        ),
        version=_int(d.get("v"), SCHEMA_VERSION),
    )


def parse_event(raw: bytes | str, zone: str) -> EventMsg:
    d = _decode(raw)
    event_type = _str(d.get("type"))
    if event_type not in EVENT_TYPES:
        raise ValueError(f"알 수 없는 event type: {event_type!r}")
    return EventMsg(
        zone=zone,
        ts=_float(d.get("ts"), time.time()),
        seq=_int(d.get("seq")),
        type=event_type,
        level=clamp_level(d.get("level")),
        details=_str(d.get("details")),
        text=_str(d.get("text")),
        provider=_str(d.get("provider")),
        fallback_reason=_str(d.get("fallback_reason")),
        emergency=_bool(d.get("emergency")),
    )


def parse_online(raw: bytes | str, zone: str) -> OnlineMsg:
    d = _decode(raw)
    return OnlineMsg(zone=zone, online=_bool(d.get("online")), ts=_float(d.get("ts"), time.time()))
