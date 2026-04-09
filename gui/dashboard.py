"""
관제 대시보드 GUI (승훈님 담당)

실시간 센서 현황, 카메라 영상, 경보 상태를 표시하는 대시보드입니다.
Phase 2 (4주차)에 개발 예정.
"""

import streamlit as st
import cv2
import threading
import time
import sys
import os

# 상위 폴더(루트 경로)의 모듈들을 불러오기 위해 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from sensors import smoke, gas, temperature, fusion
from vision import cctv_service, fire_detector
from rag.loader import load_and_split
from rag.retriever import build_vectorstore, get_retriever
from rag.chain import build_qa_chain
from voice import stt, tts

# 페이지 설정
st.set_page_config(layout="wide", page_title="EDGE SAVER TACTICAL")

@st.cache_resource
def init_tactical_engine():
    
    vector_db = build_vectorstore(load_and_split())
    qa_chain = build_qa_chain(get_retriever(vector_db))
   
    stt_model = stt._load_model()
    pa = stt._get_pyaudio_instance()
    stream = stt._open_stream(pa)
    tts_helper = tts.TTSHelper()
    
    return qa_chain, stt_model, pa, stream, tts_helper

# 시스템 엔진 로드
qa, stt_model, pa, stream, tts_helper = init_tactical_engine()

# CCTV 백그라운드 스레드 가동
if 'cam_started' not in st.session_state:
    threading.Thread(target=cctv_service.camera_worker_thread, daemon=True).start()
    st.session_state.cam_started = True

# 대화 세션 상태 관리
if 'last_answer' not in st.session_state:
    st.session_state.last_answer = ""
if 'is_first_alert' not in st.session_state:
    st.session_state.is_first_alert = True

dashboard_pos = st.empty()

# --- [TACTICAL MONITORING LOOP] ---
while True:
    with dashboard_pos.container():
        # [A. 상황 데이터 수집]
        s_val = smoke.read_smoke_level(simulate=True)
        g_val = gas.read_gas_level(simulate=True)
        t_data = temperature.read_temperature(simulate=True)
        frame = cctv_service.latest_frame
        
        fire_detected = False
        if frame is not None:
            tmp_path = "vision/captures/live_temp.jpg"
            cv2.imwrite(tmp_path, frame)
            analysis = fire_detector.detect_fire(tmp_path)
            fire_detected = analysis['fire_detected']
            display_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # 위험 판정
        risk = fusion.calculate_risk_level(s_val, g_val, t_data, fire_detected)
        level = risk['level']

        # [B. 긴급 경보 시각 효과 (Level 4+)]
        if level >= 4:
            st.markdown("""
                <style>
                .stApp { background-color: #ff000033; animation: alert_pulse 0.8s infinite; }
                @keyframes alert_pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
                </style>
                """, unsafe_allow_html=True)
        else:
            st.markdown("<style>.stApp { background-color: #0e1117; }</style>", unsafe_allow_html=True)
            st.session_state.is_first_alert = True # 정상화 시 초기화

        # [C. 레이아웃 배치]
        main_col, side_col = st.columns([2.5, 1])

        # 좌측: 실시간 카메라 영상
        with main_col:
            if frame is not None:
                st.image(display_frame, use_container_width=True)
                if fire_detected: st.error(f"⚠️ [FIRE DETECTED] {analysis['description'].upper()}")
            else:
                st.error("VIDEO SIGNAL LOST")

        # 우측: 전술 데이터 (상단 센서 / 하단 게이지)
        with side_col:
            st.markdown("### 📊 SENSOR DATA")
            st.metric("TEMPERATURE", f"{t_data['temperature']}°C")
            st.metric("SMOKE / GAS", f"{s_val} / {g_val}")
            
            st.divider()
            
            st.markdown("### 🚨 RISK GAUGE")
            g_color = "#ff0000" if level >= 4 else "#ffa500" if level >= 2 else "#00ff00"
            st.markdown(f"""
                <div style="background-color:#111; border:1px solid #444; width:100%; height:45px; border-radius:5px;">
                    <div style="background-color:{g_color}; width:{level*20}%; height:100%; border-radius:5px; transition:0.5s;"></div>
                </div>
                <h2 style='text-align:center; color:{g_color}; font-weight:bold;'>{risk['label'].upper()} (LV.{level})</h2>
            """, unsafe_allow_html=True)

        # --- [AI 선제 개입 및 연속 질의 모드] ---
        st.divider()
        st.markdown("### 🧠 AI 매뉴얼 대응 지침")

        if level >= 4:
            # 1. AI 최초 개입 (자동 RAG 긴급 브리핑 송출)
            if st.session_state.is_first_alert:
                st.warning("🚨 [시스템] '진짜 화재'로 판정되어 AI가 즉각 대응 매뉴얼을 수립합니다!")
                prompt = f"경고: 공장 내 센서와 CCTV 교차 검증 결과, 실제 화재 및 위험 상황이 확정되었습니다. (위험도: LV.{level}). 근무자들을 위한 즉각적인 비상 대피 요령을 가장 중요한 1~2문장으로 짧고 강하게 방송용으로 말해줘."
                response = qa.invoke(prompt)
                st.session_state.last_answer = response['result']
                
                tts_helper.speak(f"위험 감지. {response['result']}", lang='ko')
                st.session_state.is_first_alert = False

            # 2. 연속 질의 루프 (추가 질의 모드)
            with st.status("🎤 [QUERY MODE] 추가 매뉴얼 질문을 위한 관제사 음성 대기 중...", expanded=True):
                # 관제사 음성 경청
                query, lang = stt.listen_once(model=stt_model, pa=pa, stream=stream, use_wake_word=False)
                
                if query:
                    st.write(f"🗣️ 관제사 질문: **{query}**")
                    # RAG 매뉴얼 검색
                    response = qa.invoke(query)
                    st.session_state.last_answer = response['result']
                    
                    # AI 답변 낭독 (끝날 때까지 대기)
                    tts_helper.speak(response['result'], lang=lang)
                    
                    # 다시 질문을 받기 위해 화면 즉시 갱신
                    st.rerun()
                else:
                    st.write("질문을 대기 중입니다. (침묵 시 센서 업데이트)")

        # 지침 상시 노출 (가장 최근 답변)
        if st.session_state.last_answer:
            st.warning(f"🤖 **매뉴얼 지침**: {st.session_state.last_answer}")

    time.sleep(1)
