"""
gui/edge_publisher.py
=====================
Pi 쪽 MQTT 발행 모듈. main.py 가 판단한 결과를 관제 대시보드로 내보낸다.

원칙
    - main.py 를 절대 멈추지 않는다. 브로커가 없거나 끊겨도 모든 함수는 즉시 반환하고
      예외를 밖으로 내보내지 않는다. 재연결은 paho 백그라운드 스레드가 맡는다.
    - 판단은 하지 않는다. main.py 가 계산한 값을 그대로 옮긴다.
    - JPEG 인코딩은 별도 스레드에서 EDGE_FRAME_FPS 이하로만 한다.

main.py 연결 방법은 gui/MAIN_INTEGRATION.md 참고.

    from gui import edge_publisher as edge
    edge.start()                                   # initialize() 에서 한 번
    edge.publish_monitor(temp=temp, gas=gas, smoke=smoke, risk=risk, analysis=analysis,
                         level=self.current_level, alarm=self._alarm_active,
                         frame=frame if fresh else None)
    edge.publish_event("alarm_start", level=level, details=sensor_info,
                       text=EMERGENCY_GUIDANCE, provider="fixed")
    edge.publish_guidance(result, emergency=job["emergency"], text=text)
    edge.publish_event("alarm_end")
    edge.close()                                   # cleanup() 에서
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Mapping, Optional

from gui import mqtt_settings as S
from gui.protocol import (
    AIState,
    ProviderState,
    Zones,
    EVENT_ALARM_END,
    EVENT_ALARM_START,
    EVENT_GUIDANCE,
    build_event,
    build_online,
    build_status,
    clamp_level,
)

LOG = logging.getLogger(__name__)

_MAX_QUEUED = 100      # 끊긴 동안 쌓아둘 QoS1 이벤트 최대 개수
_CLOSE_WAIT = 1.0      # 종료 시 offline 메시지 전송 대기 (초)


def read_provider_state() -> Optional[ProviderState]:
    """Pi 의 rag/provider.py 에서 AI 모드와 Gemini 재시도 대기 시간을 읽는다.

    rag/provider.py 는 다른 담당 파일이라 고치지 않고 읽기만 한다. 재시도 시각은 공개 함수가 없어
    모듈 변수 _failure_until(time.monotonic 기준)을 읽는다. 이름이 바뀌면 재시도 시간만 0 으로 보낸다.
    읽을 수 없으면 None (status 에 provider 를 넣지 않음)."""
    try:
        import config
        from rag import provider as P

        mode = P.get_ai_mode()
        failure_until = float(getattr(P, "_failure_until", 0.0) or 0.0)
        retry_in = max(0.0, failure_until - time.monotonic()) if mode == "auto" else 0.0
        return ProviderState(
            mode=mode,
            gemini_key=bool(getattr(config, "GEMINI_API_KEY", "")),
            retry_in=retry_in,
            cooldown=float(getattr(config, "GEMINI_RETRY_COOLDOWN", 0.0) or 0.0),
        )
    except Exception:
        LOG.debug("[edge] AI 공급자 상태 읽기 실패", exc_info=True)
        return None


def encode_frame(
    frame: Any,
    analysis: Optional[Mapping[str, Any]] = None,
    width: int = S.FRAME_WIDTH,
    quality: int = S.JPEG_QUALITY,
) -> Optional[bytes]:
    """BGR ndarray → 축소 + 감지 박스 + JPEG bytes. 실패하면 None."""
    import cv2

    if frame is None or getattr(frame, "ndim", 0) != 3:
        return None
    h, w = frame.shape[:2]
    if h == 0 or w == 0:
        return None
    scale = min(1.0, width / float(w))
    img = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) \
        if scale < 1.0 else frame.copy()

    analysis = analysis or {}
    box = analysis.get("box")
    if isinstance(box, (list, tuple)) and len(box) == 4:
        try:
            x1, y1, x2, y2 = (int(v * scale) for v in box)
            if analysis.get("fire_detected"):
                color = (0, 0, 255)          # 빨강: 검증된 불꽃
            elif analysis.get("is_real_smoke"):
                color = (0, 140, 255)        # 주황: 검증된 상승 연기 (감지 결과 계약 v1 은 fire_detected=false)
            elif analysis.get("is_static_photo"):
                color = (0, 200, 255)        # 노랑: 사진 오탐 차단
            else:
                color = (200, 200, 200)      # 회색: 약한 감지
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            status = str(analysis.get("status", ""))[:28]
            if status:
                cv2.putText(img, status, (x1, max(12, y1 - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
        except (TypeError, ValueError):
            pass

    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    return buf.tobytes() if ok else None


class EdgePublisher:
    """구역 하나의 발행기. 스레드 안전, 예외를 밖으로 내보내지 않음."""

    def __init__(
        self,
        zone: str,
        *,
        sensor_mode: str = "demo",
        detection_zone: Optional[str] = None,
        host: str = S.BROKER_HOST,
        port: int = S.BROKER_PORT,
        enabled: bool = S.PUBLISH_ENABLED,
        status_interval: float = S.STATUS_INTERVAL,
        frame_fps: float = S.FRAME_FPS,
        client_factory: Optional[Callable[[str], Any]] = None,
        provider_state: Optional[Callable[[], Optional[ProviderState]]] = read_provider_state,
    ) -> None:
        self.zone = zone
        self.sensor_mode = sensor_mode
        self.detection_zone = detection_zone or zone
        self.host, self.port = host, port
        self.enabled = enabled
        self.status_interval = status_interval
        self.frame_fps = frame_fps
        self._client_factory = client_factory or S.new_client
        self.provider_state = provider_state or (lambda: None)

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._frame_ready = threading.Event()
        self._client: Any = None
        self._started = False
        self._connected = False
        self._seq = 0
        self._ai = AIState()
        self._last_status_at = 0.0
        self._last_key: tuple = ()
        self._frame: Any = None
        self._frame_analysis: Mapping[str, Any] = {}
        self._frame_thread: Optional[threading.Thread] = None

    # ── 상태 조회 ──
    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def ai_state(self) -> AIState:
        with self._lock:
            return self._ai

    # ── 연결 ──
    def start(self) -> None:
        """처음 한 번만 연결을 시작한다. 실패해도 조용히 비활성화된다."""
        with self._lock:
            if self._started:
                return
            self._started = True
        if not self.enabled:
            LOG.info("[edge] EDGE_PUBLISH=false — 관제 발행 비활성화")
            return
        try:
            client = self._client_factory(f"edge-saver-{self.zone}-{int(time.time())}")
            client.will_set(S.topic(self.zone, S.KIND_ONLINE), build_online(self.zone, False), qos=1, retain=True)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.reconnect_delay_set(min_delay=1, max_delay=30)
            if hasattr(client, "max_queued_messages_set"):
                client.max_queued_messages_set(_MAX_QUEUED)
            client.connect_async(self.host, self.port, keepalive=S.KEEPALIVE)
            client.loop_start()
            self._client = client
            LOG.info("[edge] 관제 발행 시작 → %s:%s (%s구역)", self.host, self.port, self.zone)
        except Exception as exc:
            self._client = None
            LOG.warning("[edge] 관제 발행 비활성화: %s", exc)
            return
        if self.frame_fps > 0:
            self._frame_thread = threading.Thread(target=self._frame_loop, name="edge-frame", daemon=True)
            self._frame_thread.start()

    def _on_connect(self, client, _userdata, _flags, rc, *_args) -> None:
        failed = rc.is_failure if hasattr(rc, "is_failure") else rc != 0
        if failed:
            LOG.warning("[edge] 브로커 연결 거부: %s", rc)
            return
        self._connected = True
        self._last_status_at = 0.0     # 재연결 직후 상태를 바로 보낸다
        try:
            client.publish(S.topic(self.zone, S.KIND_ONLINE), build_online(self.zone, True), qos=1, retain=True)
        except Exception:
            LOG.debug("[edge] online 발행 실패", exc_info=True)
        LOG.info("[edge] 브로커 연결됨")

    def _on_disconnect(self, *_args) -> None:
        if self._connected:
            LOG.warning("[edge] 브로커 연결 끊김 — 자동 재연결 시도")
        self._connected = False

    def _publish(self, kind: str, payload: bytes, qos: int = 0, retain: bool = False) -> bool:
        client = self._client
        if client is None:
            return False
        if qos == 0 and not self._connected:
            return False   # 끊긴 동안의 status/frame 은 버린다 (재연결 시 최신값을 다시 보냄)
        try:
            client.publish(S.topic(self.zone, kind), payload, qos=qos, retain=retain)
            return True
        except Exception:
            LOG.debug("[edge] %s 발행 실패", kind, exc_info=True)
            return False

    # ── 1. 감시 주기 상태 ──
    def publish_monitor(
        self,
        *,
        temp: Mapping[str, Any],
        gas: Any,
        smoke: Any,
        risk: Mapping[str, Any],
        analysis: Mapping[str, Any],
        level: Optional[int] = None,
        alarm: bool = False,
        frame: Any = None,
        sensor_mode: Optional[str] = None,
        fire_zone: Optional[str] = None,
    ) -> None:
        """main.py _monitor_once 에서 매 주기 호출. 실제 발행은 STATUS_INTERVAL 마다,
        위험도·경보·조기감지 상태가 바뀌면 즉시."""
        try:
            self.start()
            if self._client is None:
                return
            if frame is not None and self.frame_fps > 0:
                with self._lock:
                    self._frame, self._frame_analysis = frame, dict(analysis or {})
                self._frame_ready.set()

            shown = clamp_level(risk.get("level", 0) if level is None else level)
            try:
                provider = self.provider_state()
            except Exception:   # AI 상태를 못 읽어도 센서·경보 status 는 보낸다
                LOG.debug("[edge] provider_state 실패", exc_info=True)
                provider = None
            # AI 모드 변경, Gemini 재시도 대기 시작·종료도 즉시 보낸다
            key = (shown, bool(alarm), bool(risk.get("is_early_detection")),
                   provider.mode if provider else "", bool(provider and provider.cooling))
            now = time.monotonic()
            if key == self._last_key and now - self._last_status_at < self.status_interval:
                return
            payload = build_status(
                self.zone,
                sensor_mode=sensor_mode or self.sensor_mode,
                temp=temp, gas=gas, smoke=smoke, risk=risk, level=shown,
                analysis=analysis or {}, alarm=alarm, ai=self.ai_state, provider=provider,
                zones=Zones(local=self.zone, detection=self.detection_zone,
                            fire=(fire_zone or "") if alarm else ""),
            )
            if self._publish(S.KIND_STATUS, payload, qos=0, retain=True):
                self._last_key, self._last_status_at = key, now
        except Exception:
            LOG.debug("[edge] status 처리 실패", exc_info=True)

    # ── 2. 사건 ──
    def publish_event(self, event_type: str, **fields: Any) -> None:
        """alarm_start / guidance / warning / alarm_end. 끊긴 동안에도 QoS1 로 쌓아 두었다가 보낸다.

        status 의 ai 는 Pi 가 반복 방송하는 내용(main.py _cached_evac_guidance)처럼
        경보 시작 안내 → 구역 대피로 → 추가 대응 수칙을 이어 붙인다."""
        try:
            self.start()
            now = time.time()
            with self._lock:
                self._seq += 1
                seq = self._seq
                if event_type == EVENT_ALARM_START:
                    self._ai = AIState(str(fields.get("text", "")), str(fields.get("provider", "fixed")), "", now)
                elif event_type == EVENT_GUIDANCE and fields.get("emergency"):
                    text = str(fields.get("text", ""))
                    joined = "\n".join(filter(None, [self._ai.text, text]))
                    self._ai = AIState(joined, str(fields.get("provider", "")),
                                       str(fields.get("fallback_reason", "")), now)
                elif event_type == EVENT_ALARM_END:
                    self._ai = AIState()
                self._last_status_at = 0.0   # 다음 status 에 새 AI 상태를 바로 반영
            self._publish(S.KIND_EVENT, build_event(self.zone, seq, event_type, ts=now, **fields), qos=1)
        except Exception:
            LOG.debug("[edge] event 처리 실패", exc_info=True)

    # ── 3. 카메라 프레임 ──
    def _frame_loop(self) -> None:
        interval = 1.0 / self.frame_fps
        while not self._stop.is_set():
            if not self._frame_ready.wait(0.5):
                continue
            self._frame_ready.clear()
            with self._lock:
                frame, analysis = self._frame, self._frame_analysis
                self._frame = None
            if frame is not None and self._connected:
                try:
                    data = encode_frame(frame, analysis)
                    if data:
                        self._publish(S.KIND_FRAME, data, qos=0)
                except Exception:
                    LOG.debug("[edge] frame 인코딩 실패", exc_info=True)
            self._stop.wait(interval)

    # ── 종료 ──
    def close(self) -> None:
        self._stop.set()
        self._frame_ready.set()
        client, self._client = self._client, None
        if client is None:
            return
        try:
            if self._connected:
                info = client.publish(S.topic(self.zone, S.KIND_ONLINE), build_online(self.zone, False),
                                      qos=1, retain=True)
                try:
                    info.wait_for_publish(timeout=_CLOSE_WAIT)
                except Exception:
                    pass
                self._connected = False   # 의도한 종료를 "연결 끊김" 경고로 남기지 않게 먼저 내림
                client.disconnect()
                client.loop_stop()
            else:
                # 연결 시도 중이면 loop_stop 이 최대 수 초 기다린다. 보낼 것도 없으니 종료를 막지 않게 뒤에서 정리.
                client.disconnect()
                threading.Thread(target=client.loop_stop, name="edge-close", daemon=True).start()
        except Exception:
            LOG.debug("[edge] 종료 정리 실패", exc_info=True)
        self._connected = False


# ════════════════════════════════════════════════════════════════
#  main.py 에서 쓰는 모듈 함수 (프로세스당 발행기 하나)
# ════════════════════════════════════════════════════════════════

_default: Optional[EdgePublisher] = None
_default_lock = threading.Lock()


def get_publisher() -> EdgePublisher:
    global _default
    with _default_lock:
        if _default is None:
            try:
                import config
                zone, mode = config.ZONE_ID, config.SENSOR_MODE
                detection = getattr(config, "DETECTION_ZONE_ID", zone)
            except Exception:
                zone, mode, detection = "A", "demo", "A"
            _default = EdgePublisher(zone, sensor_mode=mode, detection_zone=detection)
        return _default


def start() -> None:
    """main.py initialize() 에서 한 번 호출 권장. 첫 연결 준비(paho import·스레드 시작, 약 0.15초)를
    감시 루프 밖에서 끝낸다. 호출하지 않아도 첫 publish 때 자동으로 시작한다."""
    try:
        get_publisher().start()
    except Exception:
        LOG.debug("[edge] start 실패", exc_info=True)


def publish_monitor(**kwargs: Any) -> None:
    try:
        get_publisher().publish_monitor(**kwargs)
    except Exception:
        LOG.debug("[edge] publish_monitor 실패", exc_info=True)


def publish_event(event_type: str, **kwargs: Any) -> None:
    try:
        get_publisher().publish_event(event_type, **kwargs)
    except Exception:
        LOG.debug("[edge] publish_event 실패", exc_info=True)


def publish_guidance(result: Any, emergency: bool = False, text: Optional[str] = None, **fields: Any) -> None:
    """rag.provider.GuidanceResult 를 그대로 받는다. main.py 쪽에서 속성을 꺼내다
    예외가 나면 이후 음성 안내까지 막히므로, 필드 읽기도 이 함수 안에서 한다.

    text: 실제로 방송한 문장 (main.py 가 중복을 걸러 낸 결과). 주지 않으면 result.text.
    비상 지침인데 방송할 문장이 비었으면 (AI 실패, 추가 수칙 없음) 보내지 않는다."""
    try:
        spoken = str(getattr(result, "text", "") or "") if text is None else str(text or "")
        if emergency and not spoken:
            return
        publish_event(
            EVENT_GUIDANCE,
            text=spoken,
            provider=str(getattr(result, "provider", "") or ""),
            fallback_reason=str(getattr(result, "fallback_reason", "") or ""),
            emergency=bool(emergency),
            **fields,
        )
    except Exception:
        LOG.debug("[edge] publish_guidance 실패", exc_info=True)


def close() -> None:
    global _default
    with _default_lock:
        pub, _default = _default, None
    if pub is not None:
        pub.close()
