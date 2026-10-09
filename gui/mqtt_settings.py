"""
gui/mqtt_settings.py
====================
Pi 발행기(edge_publisher)와 관제 대시보드가 함께 쓰는 MQTT 설정.

모든 값은 환경 변수(.env)로 바꿀 수 있다. config.py를 고치지 않기 위해
gui 폴더 안에서 따로 읽는다.

    MQTT_BROKER_HOST   브로커 주소. Pi에서는 127.0.0.1, 관제 PC에서는 Pi의 IP
    MQTT_BROKER_PORT   기본 1883
    MQTT_TOPIC_PREFIX  기본 edge  → edge/{zone}/status ...
    EDGE_PUBLISH       Pi 발행 on/off (기본 true)
    EDGE_STATUS_INTERVAL  상태 발행 주기 초 (기본 1.0)
    EDGE_FRAME_FPS     카메라 JPEG 초당 장수 (기본 3, 0이면 영상 미전송)
    EDGE_FRAME_WIDTH   전송 프레임 가로 픽셀 (기본 320)
    EDGE_JPEG_QUALITY  JPEG 품질 1~100 (기본 60)
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "127.0.0.1")
BROKER_PORT = _env_int("MQTT_BROKER_PORT", 1883)
KEEPALIVE = 10
TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "edge").strip("/") or "edge"

PUBLISH_ENABLED = os.getenv("EDGE_PUBLISH", "true").lower() == "true"
STATUS_INTERVAL = max(0.2, _env_float("EDGE_STATUS_INTERVAL", 1.0))
FRAME_FPS = max(0.0, min(_env_float("EDGE_FRAME_FPS", 3.0), 10.0))
FRAME_WIDTH = max(160, _env_int("EDGE_FRAME_WIDTH", 320))
JPEG_QUALITY = max(1, min(_env_int("EDGE_JPEG_QUALITY", 60), 100))

# 마지막 status 수신 후 이 시간이 지나면 대시보드는 "신호 지연"으로 표시한다.
STALE_SECONDS = max(2.0, STATUS_INTERVAL * 5)

# 메시지 형식이 바뀌면 올린다. 대시보드는 모르는 버전도 읽을 수 있는 필드만 사용한다.
SCHEMA_VERSION = 1

KIND_STATUS = "status"
KIND_EVENT = "event"
KIND_FRAME = "frame"
KIND_ONLINE = "online"
KINDS = (KIND_STATUS, KIND_EVENT, KIND_FRAME, KIND_ONLINE)


def topic(zone: str, kind: str) -> str:
    """edge/{zone}/{kind}"""
    return f"{TOPIC_PREFIX}/{zone}/{kind}"


def subscribe_pattern() -> str:
    """대시보드가 모든 구역의 모든 토픽을 받기 위한 와일드카드."""
    return f"{TOPIC_PREFIX}/+/+"


def split_topic(value: str) -> tuple[str, str] | None:
    """'edge/A/status' → ('A', 'status'). 형식이 다르면 None."""
    parts = value.split("/")
    prefix = TOPIC_PREFIX.split("/")
    if len(parts) != len(prefix) + 2 or parts[:len(prefix)] != prefix:
        return None
    zone, kind = parts[-2], parts[-1]
    if not zone or kind not in KINDS:
        return None
    return zone, kind


def new_client(client_id: str = ""):
    """paho-mqtt 1.x / 2.x 모두에서 동작하는 Client 생성."""
    import paho.mqtt.client as mqtt

    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    return mqtt.Client(client_id=client_id)
