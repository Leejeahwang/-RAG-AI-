"""
gui/dashboard.py - EDGE SAVER 메인 엔트리

책임:
    1. sys.path / cwd 설정
    2. RAG/STT/TTS 엔진 초기화 (@st.cache_resource)
    3. 백그라운드 워커 시작 (한 번만)
    4. CSS 주입, 레이아웃 렌더링
    5. shutdown 모달

각 panel/fragment 실제 렌더링은 gui/components.py 가 담당.
백그라운드 처리는 gui/workers.py 가 담당.
공유 상태는 gui/state.py 의 RUNTIME 싱글톤.
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

from voice import stt, tts  # noqa: E402
from alerts.alarm import stop_alarm  # noqa: E402

from gui.state import RUNTIME, MQTT_MODE  # noqa: E402
from gui import workers as W, components as C  # noqa: E402


@st.cache_resource(show_spinner="🔥 EDGE SAVER 시스템 기동 중...")
def init_engine():
    try:
        qa = W.NativeQA()
        tts_helper = tts.TTSHelper()
        stt_model = stt._load_model()
        pa = stt._get_pyaudio_instance()
        stream = stt._open_stream(pa) if pa is not None else None
        return qa, (stt_model, pa, stream), tts_helper
    except Exception as e:
        import traceback
        traceback.print_exc()
        RUNTIME.add_log(f"❌ 초기화 실패: {e}")
        return None, (None, None, None), None


def _on_theme_toggle() -> None:
    cur = RUNTIME.get_theme()
    RUNTIME.set_theme("light" if cur == "dark" else "dark")
    st.rerun()


def _on_shutdown_confirm(stt_bundle, tts_helper) -> None:
    RUNTIME.add_log("🔌 시스템 안전 종료")
    try:
        stop_alarm()
    except Exception as e:
        RUNTIME.add_log(f"[종료] 알람 정지 오류: {e}")
    W.shutdown_workers(stt_bundle, tts_helper)


st.set_page_config(layout="wide", page_title="EDGE SAVER", page_icon="🛡️")

qa, stt_bundle, tts_helper = init_engine()
C.inject_css(theme=RUNTIME.get_theme())

if qa is None:
    st.error("시스템 초기화 실패 — 로그를 확인하세요.")
    st.stop()

llm_queue = W.start_workers(qa, stt_bundle, tts_helper)

C.render_header(on_theme_toggle=_on_theme_toggle)
C.render_emergency_banner()
C.render_status_bar()


@st.fragment
def _render_input_widgets(llm_queue) -> None:
    """마이크 토글 + 텍스트 입력 박스 (test 파일과 UI 동일)."""
    mic_on = st.toggle(
        "🎙️ 음성 브리핑",
        value=RUNTIME.is_stt_enabled(),
        key="stt_toggle_widget",
    )
    RUNTIME.set_stt_enabled(mic_on)

    with st.expander("⌨️ 텍스트 질의", expanded=False):
        q = st.text_input("질문 입력 후 버튼 클릭", key="query_input")
        if st.button("AI 질의 전송", key="query_send"):
            text = q.strip()
            if not text:
                st.warning("질문을 입력해 주세요.")
            elif RUNTIME.is_generating():
                st.warning("현재 AI가 다른 작업을 처리 중입니다.")
            else:
                W.enqueue_query(llm_queue, text, "ko")
                RUNTIME.add_log(f"⌨️ 텍스트 질의: {text}")
                st.success("질의 전송 완료. AI 응답을 기다리세요.")


if MQTT_MODE:
    active_zone = RUNTIME.get_active_zone()
    if active_zone is None:
        C.render_zone_overview()
    else:
        C.render_zone_nav(active_zone)
        col_left, col_right = st.columns([1.4, 1], gap="large")
        with col_left:
            C.render_camera_panel()
            _render_input_widgets(llm_queue)
        with col_right:
            C.render_sensor_mini()
            C.render_risk_gauge()
            C.render_log_panel()
            C.render_ai_panel(llm_queue)
else:
    col_left, col_right = st.columns([1.4, 1], gap="large")
    with col_left:
        C.render_camera_panel()
        _render_input_widgets(llm_queue)
    with col_right:
        C.render_sensor_mini()
        C.render_risk_gauge()
        C.render_log_panel()
        C.render_ai_panel(llm_queue)

