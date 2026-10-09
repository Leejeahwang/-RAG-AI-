"""
gui/workers.py
==============
관제 대시보드 백그라운드 워커.

대시보드는 표시 전용이다. 카메라·센서·위험도 계산·경보·대피 방송은
모두 Pi 의 main.py 가 하고, 여기서는 그 결과를 MQTT 로 받기만 한다.

워커 3종:
    - mqtt_worker : edge/+/+ 구독 → RUNTIME 에 구역별 상태 반영
    - stt_worker  : 토글 기반, 관제사 음성 질의 → STT 큐
    - llm_worker  : 관제사 질의를 관제 PC 자체 RAG 로 답변 (+TTS)

각 워커는 RUNTIME 상태 객체와 stop_event 로만 통신한다.
Streamlit session_state 는 절대 만지지 않는다.

진입점:
    start_workers(qa, stt_bundle, tts_helper) → llm_queue
    shutdown_workers(stt_bundle, tts_helper)
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
from typing import Any, Optional, Tuple

from gui import mqtt_settings as S
from gui.protocol import parse_event, parse_online, parse_status
from gui.state import (
    RUNTIME,
    STTMessage,
    STT_IDLE_WAIT,
    LLM_PRIORITY_QUERY,
    detect_lang,
)

_seq = itertools.count()

# (priority, seq, kind, prompt, lang, meta)
LLMItem = Tuple[int, int, str, str, str, dict]

_MAX_FRAME_BYTES = 2 * 1024 * 1024


# ════════════════════════════════════════════════════════════════
#  Native RAG QA 어댑터 (FAISS + BM25 + Gemini/Ollama)
# ════════════════════════════════════════════════════════════════

class NativeQA:
    """관제사 질의용 RAG 어댑터.

    rag.native_retriever(FAISS+BM25 하이브리드) 검색 + rag.provider.generate_guidance
    를 묶어 qa.invoke(prompt) -> {"result", "provider", "fallback_reason"} 로 노출한다.

    faiss / sentence_transformers 의존성은 인스턴스 생성 시점에만 로드되므로,
    이 모듈 import 자체는 해당 패키지 없이도 성공한다."""

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

    def invoke(self, prompt: str, layout_text: str = "", emergency: bool = False) -> dict:
        import config
        from rag.provider import generate_guidance
        from rag.layout import layout_for_question

        docs = self._rag.search(prompt)
        context = "\n\n".join(self._clean(d) for d in docs)
        # 평면도가 있으면 컨텍스트 맨 앞(1순위)에 강제 주입
        if not layout_text:
            layout_text = layout_for_question(prompt)
        if layout_text:
            context = layout_text + context
        cloud_context = context if config.GEMINI_SEND_LAYOUT else "\n\n".join(self._clean(d) for d in docs)
        result = generate_guidance(context, prompt, emergency=emergency, cloud_context=cloud_context)
        return {"result": result.text, "provider": result.provider, "fallback_reason": result.fallback_reason}


# ════════════════════════════════════════════════════════════════
#  MQTT 수신
# ════════════════════════════════════════════════════════════════

def handle_message(topic: str, payload: bytes, rx: Optional[float] = None) -> bool:
    """MQTT 메시지 1개를 RUNTIME 에 반영. 처리했으면 True.

    on_message 콜백과 테스트가 함께 쓰도록 paho 객체와 분리했다."""
    parsed = S.split_topic(topic)
    if parsed is None:
        return False
    zone, kind = parsed
    try:
        if kind == S.KIND_STATUS:
            RUNTIME.apply_status(parse_status(payload, zone), rx)
        elif kind == S.KIND_EVENT:
            RUNTIME.apply_event(parse_event(payload, zone), rx)
        elif kind == S.KIND_ONLINE:
            RUNTIME.apply_online(parse_online(payload, zone), rx)
        elif kind == S.KIND_FRAME:
            if not payload or len(payload) > _MAX_FRAME_BYTES or payload[:2] != b"\xff\xd8":
                raise ValueError("JPEG 아님")
            RUNTIME.apply_frame(zone, bytes(payload), rx)
        return True
    except ValueError as e:
        RUNTIME.add_log(f"❌ [MQTT] {topic} 형식 오류: {e}")
        return False


def mqtt_worker(stop_event: threading.Event) -> None:
    """edge/+/+ 구독. 끊기면 paho 가 자동 재연결하고, 재연결마다 다시 구독한다."""
    target = f"{S.BROKER_HOST}:{S.BROKER_PORT}"
    RUNTIME.set_broker(False, "연결 중", target)
    try:
        client = S.new_client(f"edge-saver-dashboard-{int(time.time())}")
    except ImportError:
        RUNTIME.set_broker(False, "paho-mqtt 미설치")
        RUNTIME.add_log("❌ [MQTT] paho-mqtt 없음. pip install paho-mqtt")
        return

    def on_connect(c, _userdata, _flags, rc, *_):
        failed = rc.is_failure if hasattr(rc, "is_failure") else rc != 0
        if failed:
            RUNTIME.set_broker(False, f"연결 거부: {rc}")
            return
        c.subscribe(S.subscribe_pattern(), qos=1)
        RUNTIME.set_broker(True)
        RUNTIME.add_log(f"🟢 [MQTT] 브로커 연결 → {target}")

    def on_disconnect(*_args):
        connected, _, _ = RUNTIME.get_broker()
        if connected:
            RUNTIME.add_log("🔴 [MQTT] 브로커 연결 끊김 — 재연결 시도")
        RUNTIME.set_broker(False, "연결 끊김")

    def on_message(_c, _userdata, msg):
        try:
            handle_message(msg.topic, msg.payload)
        except Exception as e:
            RUNTIME.add_log(f"❌ [MQTT] 처리 오류: {e}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    try:
        client.connect_async(S.BROKER_HOST, S.BROKER_PORT, keepalive=S.KEEPALIVE)
        client.loop_start()
    except Exception as e:
        RUNTIME.set_broker(False, str(e))
        RUNTIME.add_log(f"❌ [MQTT] 브로커 연결 실패: {e}")
        return
    RUNTIME.add_log(f"📡 [MQTT] {S.subscribe_pattern()} 구독 대기 → {target}")
    stop_event.wait()
    try:
        client.disconnect()
        client.loop_stop()
    except Exception:
        pass
    RUNTIME.set_broker(False, "종료")
    RUNTIME.add_log("🛑 [MQTT] 수신 종료")


# ════════════════════════════════════════════════════════════════
#  STT worker
# ════════════════════════════════════════════════════════════════

def stt_worker(stop_event: threading.Event, model, pa, stream) -> None:
    if pa is None or stream is None:
        RUNTIME.add_log("⚠️ [STT] 마이크 없음 — 음성 인식 비활성화 (텍스트 전용 모드)")
        stop_event.wait()
        return
    from voice import stt as stt_module

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
#  LLM worker (관제사 질의 전용)
# ════════════════════════════════════════════════════════════════

def llm_worker(
    stop_event: threading.Event,
    q: "queue.PriorityQueue[LLMItem]",
    qa: Any,
    tts_helper: Any,
) -> None:
    RUNTIME.add_log("🤖 [LLM] 관제사 질의 워커 시작")
    while not stop_event.is_set():
        try:
            item = q.get(timeout=0.5)
        except queue.Empty:
            continue

        _prio, _seq_id, _kind, prompt, lang, _meta = item
        RUNTIME.set_generating(True)
        try:
            res = qa.invoke(prompt)
            answer = res.get("result", "").strip() if isinstance(res, dict) else str(res)
            provider = res.get("provider", "unknown") if isinstance(res, dict) else "unknown"
            reason = res.get("fallback_reason", "") if isinstance(res, dict) else ""
            RUNTIME.add_log(f"🤖 [AI] {provider}" + (f" (Gemini 전환: {reason})" if reason else ""))
            RUNTIME.set_last_answer(answer, provider)
            RUNTIME.add_log("✅ [LLM] 응답 완료")
            if tts_helper is not None:
                try:
                    tts_helper.speak(answer, lang=lang)
                except Exception as e:
                    RUNTIME.add_log(f"❌ [TTS] {e}")
        except Exception as e:
            RUNTIME.add_log(f"❌ [LLM] {e}")
        finally:
            RUNTIME.set_generating(False)
    RUNTIME.add_log("🛑 [LLM] 종료")


def enqueue_query(q: "queue.PriorityQueue[LLMItem]", text: str, lang: str) -> None:
    item: LLMItem = (LLM_PRIORITY_QUERY, next(_seq), "query", text, lang, {})
    try:
        q.put_nowait(item)
    except queue.Full:
        RUNTIME.add_log("⚠️ [LLM] 큐 가득 — 질의 드롭")


# ════════════════════════════════════════════════════════════════
#  Lifecycle
# ════════════════════════════════════════════════════════════════

_threads: list = []
_llm_queue: Optional["queue.PriorityQueue[LLMItem]"] = None
_started = False


def start_workers(qa: Any, stt_bundle: tuple, tts_helper: Any) -> "queue.PriorityQueue[LLMItem]":
    """모든 워커를 시작. 중복 호출 방지 (idempotent).

    qa 가 None 이면 (RAG 초기화 실패) 관제사 질의만 끄고 수신·표시는 계속한다."""
    global _threads, _llm_queue, _started
    if _started and _llm_queue is not None:
        return _llm_queue

    stt_model, pa, stream = stt_bundle
    stop_event = RUNTIME.stop_event()
    _llm_queue = queue.PriorityQueue(maxsize=8)

    specs = [("mqtt", mqtt_worker, (stop_event,))]
    if qa is not None:
        RUNTIME.set_qa_ready(True)
        specs += [
            ("stt", stt_worker, (stop_event, stt_model, pa, stream)),
            ("llm", llm_worker, (stop_event, _llm_queue, qa, tts_helper)),
        ]
    else:
        RUNTIME.add_log("⚠️ [RAG] 초기화 실패 — 관제사 질의 비활성화 (수신·표시는 정상)")
    for name, target, args in specs:
        t = threading.Thread(target=target, args=args, daemon=True, name=name)
        t.start()
        _threads.append(t)

    _started = True
    RUNTIME.add_log("=" * 40)
    RUNTIME.add_log("🛡️ EDGE SAVER 관제 대시보드 수신 대기")
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
