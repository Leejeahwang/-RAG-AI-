"""
gui/dashboard.py - EDGE SAVER 원격 관제 대시보드 엔트리

구조:
    라즈베리파이 main.py ──MQTT──▶ 이 대시보드 (표시 전용)

    판단(위험도·경보·대피 방송)은 Pi 가 한다. 대시보드는 받은 값을 보여 주고,
    관제사 질문에만 관제 PC 자체 RAG 로 답한다.

실행:
    MQTT_BROKER_HOST=<Pi IP> streamlit run gui/dashboard.py

책임:
    1. sys.path / cwd 설정
    2. 관제사 질의용 RAG/STT/TTS 초기화 (@st.cache_resource, 실패해도 화면은 뜸)
    3. 백그라운드 워커 시작 (한 번만)
    4. CSS 주입, 레이아웃 렌더링

각 panel/fragment 실제 렌더링은 gui/components.py,
백그라운드 처리는 gui/workers.py, 공유 상태는 gui/state.py 의 RUNTIME.
"""

from __future__ import annotations

import os
import sys
import warnings
import logging
warnings.filterwarnings("ignore")
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
os.chdir(ROOT_DIR)

import streamlit as st  # noqa: E402

from gui.state import RUNTIME, LIVE_REFRESH  # noqa: E402
from gui import workers as W, components as C  # noqa: E402


def _init_stt():
    import config
    if not config.STT_ENABLED:
        RUNTIME.add_log("ℹ️ [STT] STT_ENABLED=false — 음성 질의 비활성화")
        return None, None, None
    from voice import stt
    model = stt._load_model()
    pa = stt._get_pyaudio_instance()
    stream = stt._open_stream(pa) if pa is not None else None
    return model, pa, stream


@st.cache_resource(show_spinner="🛡️ EDGE SAVER 관제 대시보드 기동 중...")
def init_engine():
    """관제사 질의용 엔진. 하나가 실패해도 나머지와 MQTT 수신은 계속한다."""
    qa, stt_bundle, tts_helper = None, (None, None, None), None
    try:
        qa = W.NativeQA()
    except Exception as e:
        logging.exception("RAG 초기화 실패")
        RUNTIME.add_log(f"❌ [RAG] 초기화 실패: {e}")
    if qa is not None:
        try:
            from voice import tts
            tts_helper = tts.TTSHelper()
        except Exception as e:
            RUNTIME.add_log(f"⚠️ [TTS] 초기화 실패 — 답변은 화면에만 표시: {e}")
        try:
            stt_bundle = _init_stt()
        except Exception as e:
            RUNTIME.add_log(f"⚠️ [STT] 초기화 실패 — 텍스트 질의만 사용: {e}")
    return qa, stt_bundle, tts_helper


def _on_theme_toggle() -> None:
    cur = RUNTIME.get_theme()
    RUNTIME.set_theme("light" if cur == "dark" else "dark")
    st.rerun()


st.set_page_config(layout="wide", page_title="EDGE SAVER", page_icon="🛡️")

qa, stt_bundle, tts_helper = init_engine()
C.inject_css(theme=RUNTIME.get_theme())
llm_queue = W.start_workers(qa, stt_bundle, tts_helper)

zone = C.active_zone()


@st.fragment
def _render_input_widgets(llm_queue) -> None:
    """관제사 질의: 마이크 토글 + 텍스트 입력. 관제 PC 자체 RAG 가 답한다."""
    if not RUNTIME.is_qa_ready():
        st.caption("관제 AI(RAG) 초기화 실패 — 질의 기능 꺼짐. 수신·표시는 정상 동작합니다.")
        return
    mic_on = st.toggle(
        "🎙️ 음성 질의",
        value=RUNTIME.is_stt_enabled(),
        key="stt_toggle_widget",
    )
    RUNTIME.set_stt_enabled(mic_on)

    with st.expander("⌨️ 매뉴얼 질의", expanded=False):
        st.text_input("질문 입력 후 버튼 클릭", key="query_input")
        st.button("AI 질의 전송", key="query_send", on_click=_send_query, args=(llm_queue,))
        kind, msg = st.session_state.pop("_query_msg", (None, None))
        if kind == "ok":
            st.success(msg)
        elif kind:
            st.warning(msg)


def _send_query(llm_queue) -> None:
    """전송 버튼 콜백. 전송에 성공했을 때만 입력창을 비운다 (거절되면 질문을 그대로 둔다).
    위젯 값은 화면을 다시 그리기 전인 콜백에서만 바꿀 수 있다."""
    text = st.session_state.get("query_input", "").strip()
    if not text:
        st.session_state["_query_msg"] = ("warn", "질문을 입력해 주세요.")
    elif RUNTIME.is_generating():
        st.session_state["_query_msg"] = ("warn", "현재 AI가 다른 질문을 처리 중입니다. 잠시 후 다시 전송하세요.")
    else:
        W.enqueue_query(llm_queue, text, "ko")
        RUNTIME.add_log(f"⌨️ 관제사 질의: {text}")
        st.session_state["query_input"] = ""
        st.session_state["_query_msg"] = ("ok", f"질의 전송 완료: \"{text}\" — AI 응답을 기다리세요.")


@st.fragment(run_every=LIVE_REFRESH)
def _render_live(zone, llm_queue) -> None:
    """수신값을 보여 주는 화면 전체. 1초마다 모든 패널을 같은 시점 값으로 다시 그린다.

    패널마다 따로 자동 갱신하면 갱신 요청끼리 서로 끊어 일부 패널이 옛 값에 머문다.
    그래서 자동 갱신은 이 fragment 하나만 둔다."""
    C.render_header(on_theme_toggle=_on_theme_toggle, zone=zone)
    C.render_emergency_banner()
    C.render_status_bar(zone)
    if zone is None:
        C.render_zone_overview()
        C.render_log_panel()
        return
    C.render_zone_nav(zone)
    col_left, col_right = st.columns([1.4, 1], gap="large")
    with col_left:
        C.render_camera_panel(zone)
        C.render_event_history(zone)
    with col_right:
        C.render_sensor_mini(zone)
        C.render_risk_gauge(zone)
        C.render_log_panel()
        C.render_ai_panel(zone, llm_queue)


_render_live(zone, llm_queue)
if zone is not None:
    # 입력 위젯은 자동 갱신 영역 밖에 둔다 (입력 중 화면 갱신에 끊기지 않게)
    _render_input_widgets(llm_queue)
