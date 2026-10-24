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
from typing import Any, Mapping, Optional

from gui.mqtt_settings import SCHEMA_VERSION

# 위험도 0~5 (sensors/fusion.py, config.RISK_LEVELS 와 동일)
LEVEL_LABELS = {0: "정상", 1: "주의", 2: "경고", 3: "위험", 4: "긴급", 5: "재난"}
MAX_LEVEL = 5

# rag/provider.py GuidanceResult.provider 값 → 화면 표시 이름
PROVIDER_LABELS = {
    "gemini": "Gemini",
    "ollama": "로컬 Qwen",
    "fixed": "고정 안내",
    "zone": "등록 구역 대피로",
}

# vision/smoke_motion.py 가 실제 사진으로 판정했을 때만 쓰는 상태값
PHOTO_BLOCK_STATUSES = frozenset({"STATIC_PHOTO_BLOCKED", "HANDHELD_PHOTO_BLOCKED"})
CAMERA_OFFLINE_STATUS = "CAMERA_OFFLINE"

EVENT_ALARM_START = "alarm_start"
EVENT_ALARM_END = "alarm_end"
EVENT_GUIDANCE = "guidance"
EVENT_WARNING = "warning"      # Level 2 비전 경고 (Pi 가 고정 경고 음성 1회 방송)
EVENT_TYPES = (EVENT_ALARM_START, EVENT_ALARM_END, EVENT_GUIDANCE, EVENT_WARNING)

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
    demo_bypass: bool = False   # demo 모드 시연 우회 (실제 불꽃 검증 아님)

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


# rag/provider.py 의 AI 모드 → 화면 표시 이름
AI_MODE_LABELS = {
    "auto": "자동 (Gemini 우선, 실패 시 로컬)",
    "gemini": "Gemini 우선",
    "local": "로컬 고정",
}


@dataclass(frozen=True)
class ProviderState:
    """Pi 의 답변 공급자 상태 (rag/provider.py). mode 가 빈 문자열이면 보내지 않은 것."""
    mode: str = ""              # auto | gemini | local
    gemini_key: bool = True     # GEMINI_API_KEY 설정 여부
    retry_in: float = 0.0       # Gemini 재시도까지 남은 초 (auto 모드에서 실패 후 대기 중일 때만 > 0)
    cooldown: float = 0.0       # 재시도 대기 전체 길이 (config.GEMINI_RETRY_COOLDOWN)

    @property
    def known(self) -> bool:
        return bool(self.mode)

    @property
    def cooling(self) -> bool:
        return self.retry_in > 0


@dataclass(frozen=True)
class Zones:
    """구역 구분 (main.py: local_zone=ZONE_ID, detection_zone=DETECTION_ZONE_ID).

    local: 이 Pi 가 방송하는 곳 (스피커 위치), detection: 이 Pi 의 카메라·센서가 보는 곳,
    fire: 지금 경보 중인 화재 구역 (경보가 아니면 빈 문자열). 다른 Pi 의 HTTP 경보를 받으면
    fire 가 local 과 달라진다."""
    local: str = ""
    detection: str = ""
    fire: str = ""

    @property
    def remote_fire(self) -> bool:
        return bool(self.fire and self.local and self.fire != self.local)


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
    provider: ProviderState = field(default_factory=ProviderState)
    zones: Zones = field(default_factory=Zones)
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
    fire_zone: str = ""
    local_zone: str = ""


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
    provider: Optional[ProviderState] = None,
    zones: Optional[Zones] = None,
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
            "demo_bypass": _bool(analysis.get("demo_bypass")),
        },
        "alarm": bool(alarm),
        **({"zones": {"local": _str(zones.local), "detection": _str(zones.detection),
                      "fire": _str(zones.fire)}} if zones is not None else {}),
        "ai": {
            "text": _str(ai.text),
            "provider": _str(ai.provider),
            "fallback_reason": _str(ai.fallback_reason),
            "ts": ai.ts,
        },
        **({"provider": {
            "mode": _str(provider.mode),
            "gemini_key": bool(provider.gemini_key),
            "retry_in": round(max(0.0, _float(provider.retry_in)), 1),
            "cooldown": round(max(0.0, _float(provider.cooldown)), 1),
        }} if provider is not None and provider.known else {}),
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
    for key in ("level", "details", "text", "provider", "fallback_reason", "emergency",
                "fire_zone", "local_zone"):
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
    s, r, v, a, pv, z = (_dict(d.get(k)) for k in ("sensors", "risk", "vision", "ai", "provider", "zones"))
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
            demo_bypass=_bool(v.get("demo_bypass")),
        ),
        alarm=_bool(d.get("alarm")),
        zones=Zones(local=_str(z.get("local")).upper(), detection=_str(z.get("detection")).upper(),
                    fire=_str(z.get("fire")).upper()),
        ai=AIState(
            text=_str(a.get("text")),
            provider=_str(a.get("provider")),
            fallback_reason=_str(a.get("fallback_reason")),
            ts=_float(a.get("ts")),
        ),
        provider=ProviderState(
            mode=_str(pv.get("mode")).lower(),
            gemini_key=_bool(pv.get("gemini_key", True)),
            retry_in=max(0.0, _float(pv.get("retry_in"))),
            cooldown=max(0.0, _float(pv.get("cooldown"))),
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
        fire_zone=_str(d.get("fire_zone")).upper(),
        local_zone=_str(d.get("local_zone")).upper(),
    )


def parse_online(raw: bytes | str, zone: str) -> OnlineMsg:
    d = _decode(raw)
    return OnlineMsg(zone=zone, online=_bool(d.get("online")), ts=_float(d.get("ts"), time.time()))
