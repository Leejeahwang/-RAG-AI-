"""
gui/workers.py
==============
백그라운드 워커들을 한 파일에 모음.

각 워커는 RUNTIME 상태 객체와 stop_event로만 통신한다.
Streamlit session_state는 절대 만지지 않는다.

워커 4종:
    - sensor_worker  : 1s 주기, 센서값/위험도 계산
    - fire_worker    : 2s 주기, CCTV 프레임으로 YOLO 화재 탐지
    - stt_worker     : 토글 기반, 음성 입력 → STT 큐
    - llm_worker     : PriorityQueue 소비, qa.invoke + TTS + send_alert

진입점:
    start_workers(qa, stt_bundle, tts_helper) → llm_queue
    shutdown_workers(stt_bundle, tts_helper)
"""

from __future__ import annotations

import heapq
import itertools
import os
import queue
import threading
import time
from typing import Any, Optional, Tuple

import config
from sensors import smoke, gas, temperature, fusion
from vision import cctv_service, fire_detector
from voice import stt as stt_module
from alerts.alarm import trigger_alarm
from alerts.notifier import send_alert

from gui.state import (
    RUNTIME,
    SensorSnapshot,
    FireSnapshot,
    RiskSnapshot,
    STTMessage,
    SIMULATE,
    MQTT_MODE,
    SENSOR_INTERVAL,
    FIRE_INTERVAL,
    STT_IDLE_WAIT,
    LLM_PRIORITY_EMERGENCY,
    LLM_PRIORITY_QUERY,
    ALERT_THRESHOLD,
    detect_lang,
)

_seq = itertools.count()

# (priority, seq, kind, prompt, lang, meta)
LLMItem = Tuple[int, int, str, str, str, dict]


# ════════════════════════════════════════════════════════════════
#  Native RAG QA 어댑터 (FAISS + BM25 + Ollama 스트리밍)
# ════════════════════════════════════════════════════════════════

class NativeQA:
    """새 방식 RAG 어댑터.

    rag.native_retriever(FAISS+BM25 하이브리드) 검색 + rag.chain.call_ollama_native
    스트리밍 호출을 묶어, gui가 기대하는 qa.invoke(prompt) -> {"result": str}
    인터페이스로 노출한다. (옛 build_qa_chain / Chroma 방식을 대체)

    faiss / sentence_transformers 의존성은 인스턴스 생성 시점에만 로드되므로,
    이 모듈 import 자체는 해당 패키지 없이도 성공한다(호출 측에서 폴백 가능)."""

    def __init__(self):
        from rag.native_retriever import rag_manager
        from rag.loader import load_and_split

        self._rag = rag_manager
        self._rag.load_resources()
        if not self._rag.index:
            RUNTIME.add_log("📖 [RAG] 인덱스 없음 — 매뉴얼로 신규 구축")
            chunks = load_and_split()
            self._rag.build_index(chunks)
        RUNTIME.add_log(f"✅ [RAG] Native 인덱스 준비 완료 ({len(self._rag.metadata)}개)")

    @staticmethod
    def _clean(doc: dict) -> str:
        """매뉴얼 메타데이터 헤더([위치:], [출처:], 마크다운 기호) 제거 — 앵무새/노이즈 방지."""
        lines = doc.get("page_content", "").split("\n")
        keep = [
            l for l in lines
            if "[위치:" not in l and "[출처:" not in l
            and not l.strip().startswith(("###", "---"))
        ]
        return "\n".join(keep)

    def invoke(self, prompt: str) -> dict:
        from rag.chain import call_ollama_native

        docs = self._rag.search(prompt)
        context = "\n\n".join(self._clean(d) for d in docs)
        answer = "".join(call_ollama_native(prompt=context, question=prompt))
        return {"result": answer.strip()}


# ════════════════════════════════════════════════════════════════
#  Sensor worker
# ════════════════════════════════════════════════════════════════

def sensor_worker(stop_event: threading.Event) -> None:
    RUNTIME.add_log("🟢 [센서] 감시 시작")
    while not stop_event.is_set():
        try:
            s_val = smoke.read_smoke_level(simulate=SIMULATE)
            g_val = gas.read_gas_level(simulate=SIMULATE)
            t_data = temperature.read_temperature(simulate=SIMULATE)

            now = time.time()
            RUNTIME.set_sensors(SensorSnapshot(
                smoke=int(s_val),
                gas=int(g_val),
                temperature=float(t_data.get("temperature", 0.0)),
                humidity=float(t_data.get("humidity", 0.0)),
                ts=now,
            ))

            fire = RUNTIME.get_fire()
            risk = fusion.calculate_risk_level(s_val, g_val, t_data, fire.detected)
            RUNTIME.set_risk(RiskSnapshot(
                level=int(risk["level"]),
                label=str(risk["label"]),
                details=str(risk["details"]),
                ts=now,
            ))
        except Exception as e:
            RUNTIME.add_log(f"❌ [센서] 오류: {e}")
        stop_event.wait(SENSOR_INTERVAL)
    RUNTIME.add_log("🛑 [센서] 종료")


# ════════════════════════════════════════════════════════════════
#  Fire detection worker
# ════════════════════════════════════════════════════════════════

def fire_worker(stop_event: threading.Event) -> None:
    """카메라 latest_frame → state에 반영, YOLO로 화재 탐지."""
    RUNTIME.add_log("🔥 [화재 탐지] 감시 시작")
    capture_path = config.CAPTURE_PATH

    while not stop_event.is_set():
        try:
            frame = cctv_service.latest_frame
            if frame is None:
                stop_event.wait(0.5)
                continue

            RUNTIME.set_frame(frame)

            import cv2
            cv2.imwrite(capture_path, frame)
            analysis = fire_detector.detect_fire(capture_path)

            RUNTIME.set_fire(FireSnapshot(
                detected=bool(analysis.get("fire_detected", False)),
                confidence=float(analysis.get("confidence", 0.0)),
                description=str(analysis.get("description", "")),
                ts=time.time(),
            ))

            if not analysis.get("fire_detected") and os.path.exists(capture_path):
                try:
                    os.remove(capture_path)
                except OSError:
                    pass
        except Exception as e:
            RUNTIME.add_log(f"❌ [화재 탐지] 오류: {e}")
        stop_event.wait(FIRE_INTERVAL)
    RUNTIME.add_log("🛑 [화재 탐지] 종료")


# ════════════════════════════════════════════════════════════════
#  STT worker
# ════════════════════════════════════════════════════════════════

def stt_worker(stop_event: threading.Event, model, pa, stream) -> None:
    if pa is None or stream is None:
        RUNTIME.add_log("⚠️ [STT] 마이크 없음 — 음성 인식 비활성화 (텍스트 전용 모드)")
        stop_event.wait()
        return
    RUNTIME.add_log("🎙️ [STT] 준비 완료 (토글로 활성화)")
    last_on = False
    while not stop_event.is_set():
        if not RUNTIME.is_stt_enabled():
            if last_on:
                RUNTIME.add_log("🛑 [STT] 마이크 비활성화")
                last_on = False
            stop_event.wait(STT_IDLE_WAIT)
            continue
        if not last_on:
            RUNTIME.add_log("🎙️ [STT] 마이크 활성화, 말씀해 주세요...")
            last_on = True
        try:
            query, _ = stt_module.listen_once(
                model=model, pa=pa, stream=stream, use_wake_word=False
            )
            if query:
                lang = detect_lang(query)
                RUNTIME.add_log(f"🎤 [STT] 수신({lang}): {query}")
                if not RUNTIME.push_stt(STTMessage(text=query, lang=lang, ts=time.time())):
                    RUNTIME.add_log("❌ [STT] 큐 가득 — 음성 입력 드롭")
                    RUNTIME.set_stt_dropped()
        except Exception as e:
            RUNTIME.add_log(f"❌ [STT] 오류: {e}")
            stop_event.wait(0.5)
    RUNTIME.add_log("🛑 [STT] 종료")


# ════════════════════════════════════════════════════════════════
#  LLM worker
# ════════════════════════════════════════════════════════════════

def llm_worker(
    stop_event: threading.Event,
    q: "queue.PriorityQueue[LLMItem]",
    qa: Any,
    tts_helper: Any,
) -> None:
    RUNTIME.add_log("🤖 [LLM] 워커 시작")
    while not stop_event.is_set():
        try:
            item = q.get(timeout=0.5)
        except queue.Empty:
            continue

        _prio, _seq_id, kind, prompt, lang, meta = item
        RUNTIME.set_generating(True)
        try:
            if kind == "emergency":
                trigger_alarm(meta.get("level", 0), meta.get("details", ""))
                try:
                    tts_helper.stop()
                except Exception:
                    pass
            res = qa.invoke(prompt)
            answer = res.get("result", "").strip() if isinstance(res, dict) else str(res)
            RUNTIME.set_last_answer(answer)

            if kind == "emergency":
                try:
                    send_alert(
                        zone=meta.get("zone", "A구역"),
                        risk_level=meta.get("level", 0),
                        sensor_details=meta.get("sensor_info", ""),
                        ai_guidance=answer,
                    )
                except Exception as e:
                    RUNTIME.add_log(f"❌ [알림] {e}")
                RUNTIME.add_log("📢 [LLM] 비상 지침 생성 완료, TTS 시작")
                try:
                    tts_helper.speak(f"비상 상황 발생! {answer}", lang="ko")
                except Exception as e:
                    RUNTIME.add_log(f"❌ [TTS] {e}")
            else:
                RUNTIME.add_log("✅ [LLM] 응답 완료")
                try:
                    tts_helper.speak(answer, lang=lang)
                except Exception as e:
                    RUNTIME.add_log(f"❌ [TTS] {e}")
        except Exception as e:
            RUNTIME.add_log(f"❌ [LLM] {e}")
        finally:
            RUNTIME.set_generating(False)
    RUNTIME.add_log("🛑 [LLM] 종료")


# ════════════════════════════════════════════════════════════════
#  MQTT 구독 워커 (관제 PC 모드)
# ════════════════════════════════════════════════════════════════

def mqtt_sensor_worker(stop_event: threading.Event) -> None:
    """MQTT factory/sensors/# 구독 → 구역별 센서 상태 갱신."""
    import json
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        RUNTIME.add_log("❌ [MQTT] paho-mqtt 없음. pip install paho-mqtt")
        return

    def on_message(client, userdata, msg):
        try:
            d = json.loads(msg.payload)
            zone = d.get("zone", msg.topic.split("/")[-1])
            snap = SensorSnapshot(
                smoke=int(d.get("smoke", 0)),
                gas=int(d.get("gas", 0)),
                temperature=float(d.get("temperature", 0)),
                humidity=float(d.get("humidity", 0)),
                ts=float(d.get("ts", time.time())),
            )
            RUNTIME.set_zone_sensors(zone, snap)
            fire = RUNTIME.get_zone_fire(zone)
            risk = fusion.calculate_risk_level(
                snap.smoke, snap.gas,
                {"temperature": snap.temperature, "humidity": snap.humidity},
                fire.detected,
            )
            RUNTIME.set_zone_risk(zone, RiskSnapshot(
                level=int(risk["level"]),
                label=str(risk["label"]),
                details=str(risk["details"]),
                ts=time.time(),
            ))
        except Exception as e:
            RUNTIME.add_log(f"❌ [MQTT 센서] 파싱 오류: {e}")

    client = mqtt.Client()
    client.on_message = on_message
    try:
        client.connect(config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT, 60)
    except Exception as e:
        RUNTIME.add_log(f"❌ [MQTT] 브로커 연결 실패: {e}")
        return
    client.subscribe("factory/sensors/#")
    RUNTIME.add_log(f"🟢 [MQTT] 센서 구독 시작 → {config.MQTT_BROKER_HOST}:{config.MQTT_BROKER_PORT}")
    client.loop_start()
    stop_event.wait()
    client.loop_stop()
    RUNTIME.add_log("🛑 [MQTT] 센서 구독 종료")


def mqtt_fire_worker(stop_event: threading.Event) -> None:
    """MQTT factory/fire/# 구독 → 구역별 화재 상태 갱신."""
    import json
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return

    def on_message(client, userdata, msg):
        try:
            d = json.loads(msg.payload)
            zone = d.get("zone", msg.topic.split("/")[-1])
            RUNTIME.set_zone_fire(zone, FireSnapshot(
                detected=bool(d.get("detected", False)),
                confidence=float(d.get("confidence", 0)),
                description=str(d.get("description", "")),
                ts=float(d.get("ts", time.time())),
            ))
        except Exception as e:
            RUNTIME.add_log(f"❌ [MQTT 화재] 파싱 오류: {e}")

    client = mqtt.Client()
    client.on_message = on_message
    try:
        client.connect(config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT, 60)
    except Exception as e:
        RUNTIME.add_log(f"❌ [MQTT] 화재 브로커 연결 실패: {e}")
        return
    client.subscribe("factory/fire/#")
    RUNTIME.add_log(f"🔥 [MQTT] 화재 구독 시작")
    client.loop_start()
    stop_event.wait()
    client.loop_stop()
    RUNTIME.add_log("🛑 [MQTT] 화재 구독 종료")


# ════════════════════════════════════════════════════════════════
#  Alert dispatcher (모든 구역 감시 → LLM 자동 트리거)
# ════════════════════════════════════════════════════════════════

def alert_dispatcher(
    stop_event: threading.Event,
    q: "queue.PriorityQueue[LLMItem]",
) -> None:
    """모든 구역 위험도 polling. 임계치 넘으면 사용자 시야와 무관하게 LLM enqueue."""
    RUNTIME.add_log(f"🚨 [디스패처] 모든 구역 감시 시작 (임계치 LV{ALERT_THRESHOLD})")
    while not stop_event.is_set():
        try:
            zones = RUNTIME.get_all_zones()
            for zone, sensors in zones.items():
                risk = RUNTIME.get_zone_risk(zone)
                if risk.level >= ALERT_THRESHOLD:
                    if RUNTIME.try_claim_zone_alert(zone):
                        RUNTIME.add_log(
                            f"🚨 [{zone}] 위급상황 LV{risk.level} 감지 — RAG 지침 생성 시작"
                        )
                        enqueue_emergency(q, risk, sensors, zone)
                else:
                    RUNTIME.reset_zone_alert(zone)
        except Exception as e:
            RUNTIME.add_log(f"❌ [디스패처] {e}")
        stop_event.wait(1.0)
    RUNTIME.add_log("🛑 [디스패처] 종료")


# ════════════════════════════════════════════════════════════════
#  Enqueue helpers
# ════════════════════════════════════════════════════════════════

def enqueue_emergency(
    q: "queue.PriorityQueue[LLMItem]",
    risk: RiskSnapshot,
    sensors: Optional[SensorSnapshot],
    zone: str,
) -> None:
    prompt = (
        f"경고: 공장 내 센서와 CCTV 융합 교차 검증 결과, "
        f"심각한 화재 재난 위험(LV.{risk.level})이 확정 감지되었습니다. "
        f"(원인: {risk.details}). 이 위급 상황에 맞는 뼈대가 되는 핵심 대피 지시 사항을 "
        f"방송용으로 가장 짧고 강하게 생성해줘."
    )
    sensor_info = (
        f"온도:{sensors.temperature}°C / 가스:{sensors.gas} / 연기:{sensors.smoke}"
        if sensors else "센서 데이터 없음"
    )
    item: LLMItem = (
        LLM_PRIORITY_EMERGENCY,
        next(_seq),
        "emergency",
        prompt,
        "ko",
        {
            "level": risk.level,
            "details": risk.details,
            "zone": zone,
            "sensor_info": sensor_info,
        },
    )
    try:
        q.put_nowait(item)
    except queue.Full:
        # 일반 질의(priority 10)를 제거하고 비상 요청 강제 삽입
        with q.mutex:
            for i in range(len(q.queue) - 1, -1, -1):
                if q.queue[i][0] >= LLM_PRIORITY_QUERY:
                    q.queue.pop(i)
                    heapq.heapify(q.queue)
                    heapq.heappush(q.queue, item)
                    RUNTIME.add_log("⚠️ [LLM] 일반 질의 제거 후 비상 요청 강제 삽입")
                    return
        RUNTIME.add_log("⚠️ [LLM] 큐 가득 (모두 비상) — 비상 요청 드롭")


def enqueue_query(q: "queue.PriorityQueue[LLMItem]", text: str, lang: str) -> None:
    item: LLMItem = (
        LLM_PRIORITY_QUERY,
        next(_seq),
        "query",
        text,
        lang,
        {},
    )
    try:
        q.put_nowait(item)
    except queue.Full:
        RUNTIME.add_log("⚠️ [LLM] 큐 가득 — 음성 질의 드롭")


# ════════════════════════════════════════════════════════════════
#  Lifecycle
# ════════════════════════════════════════════════════════════════

_threads: list = []
_llm_queue: Optional["queue.PriorityQueue[LLMItem]"] = None
_started = False


def start_workers(qa: Any, stt_bundle: tuple, tts_helper: Any) -> "queue.PriorityQueue[LLMItem]":
    """모든 워커를 시작. 중복 호출 방지 (idempotent)."""
    global _threads, _llm_queue, _started
    if _started and _llm_queue is not None:
        return _llm_queue

    stt_model, pa, stream = stt_bundle
    stop_event = RUNTIME.stop_event()
    _llm_queue = queue.PriorityQueue(maxsize=8)

    if not MQTT_MODE:
        cam_t = threading.Thread(target=cctv_service.camera_worker_thread, daemon=True, name="cam")
        cam_t.start()
        _threads.append(cam_t)

    if MQTT_MODE:
        specs = [
            ("mqtt_sensor", mqtt_sensor_worker, (stop_event,)),
            ("mqtt_fire", mqtt_fire_worker, (stop_event,)),
            ("alert_dispatcher", alert_dispatcher, (stop_event, _llm_queue)),
            ("stt", stt_worker, (stop_event, stt_model, pa, stream)),
            ("llm", llm_worker, (stop_event, _llm_queue, qa, tts_helper)),
        ]
    else:
        specs = [
            ("sensor", sensor_worker, (stop_event,)),
            ("fire", fire_worker, (stop_event,)),
            ("stt", stt_worker, (stop_event, stt_model, pa, stream)),
            ("llm", llm_worker, (stop_event, _llm_queue, qa, tts_helper)),
        ]
    for name, target, args in specs:
        t = threading.Thread(target=target, args=args, daemon=True, name=name)
        t.start()
        _threads.append(t)

    _started = True
    time.sleep(0.15)
    RUNTIME.add_log("=" * 40)
    RUNTIME.add_log("🔥 EDGE SAVER 감시 시스템 작동 중")
    RUNTIME.add_log("=" * 40)
    return _llm_queue


def shutdown_workers(stt_bundle: Optional[tuple] = None, tts_helper: Any = None) -> None:
    """모든 워커에 종료 신호 + 외부 자원 정리."""
    RUNTIME.request_shutdown()
    if tts_helper is not None:
        try:
            tts_helper.stop()
        except Exception as e:
            RUNTIME.add_log(f"[종료] TTS 정리 오류: {e}")
    try:
        cctv_service.camera_running = False
    except Exception:
        pass
    if stt_bundle is not None:
        _, pa, stream = stt_bundle
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass
        try:
            pa.terminate()
        except Exception:
            pass

