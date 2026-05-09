import streamlit as st
import cv2
import threading
import time
import sys
import os
import queue
import re
from collections import deque 
from streamlit.runtime.scriptrunner import add_script_run_ctx

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.chdir(ROOT_DIR)

import config
from sensors import smoke, gas, temperature, fusion
from vision import cctv_service, fire_detector
from voice import stt, tts
from alerts.alarm import trigger_alarm, stop_alarm
from alerts.notifier import send_alert

# --- 1. 세션 상태 및 로그 초기화 ---
if 'system_logs' not in st.session_state:
    st.session_state.system_logs = deque(["[18:00:00] 🔥 EDGE SAVER 감시 시스템 시작 🔥"], maxlen=50)
if 'last_answer' not in st.session_state: st.session_state.last_answer = ""
if 'is_first_alert' not in st.session_state: st.session_state.is_first_alert = True
if 'system_offline' not in st.session_state: st.session_state.system_offline = False

if 'speech_queue' not in st.session_state: st.session_state.speech_queue = queue.Queue()
if 'stt_toggle' not in st.session_state: st.session_state.stt_toggle = False
if 'theme' not in st.session_state: st.session_state.theme = "light"
if 'is_generating' not in st.session_state: st.session_state.is_generating = False # 💡 AI 작동 상태 추가

def add_log(msg):
    timestamp = time.strftime('%H:%M:%S')
    st.session_state.system_logs.append(f"[{timestamp}] {msg}")

def detect_lang(text):
    if not text: return 'ko'
    if re.search('[가-힣]', text): return 'ko'      
    if re.search('[ぁ-んァ-ヶ]', text): return 'ja'  
    if re.search('[\u4e00-\u9fff]', text): return 'zh' 
    if re.search('[a-zA-Z]', text): return 'en'     
    return 'ko'

# --- 2. 시스템 엔진 및 쓰레드 초기화 ---
@st.cache_resource 
def init_tactical_engine():
    add_log("=" * 45)
    add_log("🔥 EDGE SAVER 감시 시스템 기동 시작 🔥")
    add_log("=" * 45)
    try:
        from rag.loader import load_and_split
        from rag.retriever import build_vectorstore, get_retriever
        from rag.chain import build_qa_chain

        add_log("[시스템] 1/3: 소방 매뉴얼 로딩 중...")
        chunks = load_and_split()
        add_log("[시스템] 2/3: 벡터DB 구축 및 리트리버 설정...")
        db = build_vectorstore(chunks)
        retriever = get_retriever(db)
        add_log("[시스템] 3/3: LLM QA 체인 구성 완료...")
        qa_chain = build_qa_chain(retriever)

        add_log("[시스템] + 음성 출력(TTS) 엔진 준비 중...")
        tts_helper = tts.TTSHelper()
        add_log("[시스템] + 음성 인식(STT) 엔진 준비 중...")
        stt_model = stt._load_model()
        pa = stt._get_pyaudio_instance()
        stream = stt._open_stream(pa)

        add_log("\n✅ 시스템 모든 모듈 초기화 완료!\n")
        return qa_chain, stt_model, pa, stream, tts_helper
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"CRITICAL INIT ERROR: {e}", flush=True)
        add_log(f"❌ 초기화 실패: {e}")
        return None, None, None, None, None

qa, stt_model, pa, stream, tts_helper = init_tactical_engine()

def stt_background_worker(model, pa, stream):
    last_status = False 
    while True:
        current_toggle = st.session_state.get('stt_toggle', False)
        if current_toggle:
            if not last_status:
                add_log("🎙️ [STT] 마이크 활성화: 말씀해 주세요...")
                last_status = True
            
            query, _ = stt.listen_once(model=model, pa=pa, stream=stream, use_wake_word=False)
            if query:
                add_log("⚙️ [STT] 처리 중...") 
                st.session_state.speech_queue.put(query)
                add_log("🎙️ [STT] 말씀해 주세요...") 
        else:
            if last_status:
                add_log("🛑 [STT] 마이크 비활성화")
                last_status = False
            time.sleep(0.5)

if 'threads_started' not in st.session_state:
    cam_thread = threading.Thread(target=cctv_service.camera_worker_thread, daemon=True)
    stt_thread = threading.Thread(target=stt_background_worker, args=(stt_model, pa, stream), daemon=True)
    
    add_script_run_ctx(cam_thread)
    add_script_run_ctx(stt_thread)
    
    cam_thread.start()
    stt_thread.start()
    st.session_state.threads_started = True

# ==========================================
# [프론트엔드 UI/CSS 렌더링]
st.set_page_config(layout="wide", page_title="EDGE SAVER", page_icon="🛡️")

t = {
    "bg": "#ffffff" if st.session_state.theme == "light" else "#0e1117",
    "card": "#f1f5f9" if st.session_state.theme == "light" else "#1a1c24",
    "text": "#1e293b" if st.session_state.theme == "light" else "#cbd5e1",
    "border": "#cbd5e1" if st.session_state.theme == "light" else "#30333d",
    "title": "#0f172a" if st.session_state.theme == "light" else "#ffffff"
}

st.markdown(f"""
    <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
        html, body, [class*="css"], .stApp {{
            font-family: 'Pretendard', 'Noto Sans KR', 'Malgun Gothic', sans-serif !important;
            background-color: {t['bg']} !important;
            color: {t['text']} !important;
        }}
        .block-container {{ padding-top: 0rem !important; padding-bottom: 1rem !important; padding-left: 2% !important; padding-right: 2% !important; max-width: 1600px !important; }}
        header[data-testid="stHeader"], [data-testid="stAppDeployButton"], [data-testid="stToolbar"] {{ display: none !important; }}
        div[data-testid="stButton"] {{ display: flex; justify-content: flex-end; gap: 10px; }}
        div[data-testid="stButton"] button {{ padding: 0.2rem 1rem !important; }}
        hr {{ margin-top: 0px !important; margin-bottom: 10px !important; }}
        div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] * {{ font-size: 24px !important; font-weight: bold !important; color: {t['title']} !important; }}
        [data-testid="stMetricLabel"] p, [data-testid="stMetricLabel"] span, [data-testid="stMetricLabel"] label, [data-testid="stMetricLabel"] div {{ 
            font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif !important; font-size: 15px !important; font-weight: 800 !important; color: {t['title']} !important; letter-spacing: 0.5px !important;
        }}
        div[data-testid="stWidgetLabel"] p, div[data-testid="stWidgetLabel"] span {{
            font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif !important; font-size: 16px !important; font-weight: 800 !important; color: {t['title']} !important; letter-spacing: 0.5px !important;
        }}
        .indicator-bar {{ display: flex; gap: 8px; justify-content: space-between; margin-top: 5px; margin-bottom: 15px; }}
        .status-item {{ display: flex; flex: 1; justify-content: center; align-items: center; gap: 6px; font-size: 11px; font-weight: 800; color: {t['text']}; letter-spacing: 0.5px; background-color: {t['card']}; padding: 6px 0; border-radius: 20px; border: 1px solid {t['border']}; }}
        .dot-green {{ height: 8px; width: 8px; background-color: #22c55e; border-radius: 50%; box-shadow: 0 0 6px #22c55e; }}
        .main-title {{ text-align: center; font-size: 26px; font-weight: 800; margin: 0px !important; padding-top: 8px !important; color: {t['title']}; letter-spacing: 1px; }}
        .sub-title {{ font-size: 18px; font-weight: 700; margin-top: 10px !important; margin-bottom: 10px !important; color: {t['title']}; }}
        .ai-sub-title {{ font-size: 18px; font-weight: 700; margin-top: -5px !important; margin-bottom: 10px !important; color: {t['title']}; }}
        .gauge-container {{ width: 100%; background-color: {t['border']}; border-radius: 8px; margin-bottom: 5px; }}
        .live-badge {{ background-color: #22c55e; color: white; padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: bold; display: inline-block; margin-top: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .ai-box, .log-box {{ background-color: {t['card']}; color: {t['text']}; border-radius: 8px; padding: 15px; font-size: 14px; line-height: 1.5; white-space: pre-wrap; border: 1px solid {t['border']}; overflow-y: auto; font-family: monospace; }}
        .ai-box {{ height: 230px; }}
        .log-box {{ height: 450px; }}
    </style>
""", unsafe_allow_html=True)
# ==========================================

if st.session_state.system_offline:
    st.markdown("<div style='height: 35vh;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #ef4444; font-size: 40px;'>⚠️ 시스템이 종료되었습니다.</h1>", unsafe_allow_html=True)
    st.stop()

@st.dialog("⚠️ 시스템 전원 종료")
def shutdown_modal():
    st.write("감시 시스템을 완전히 종료하시겠습니까?")
    col1, col2 = st.columns(2)
    if col1.button("예 (YES)", type="primary", use_container_width=True):
        add_log("🔌 시스템 안전 종료...")
        try: stop_alarm() 
        except: pass
        cctv_service.camera_running = False
        try: stream.stop_stream(); stream.close(); pa.terminate(); tts_helper.stop()
        except: pass
        st.session_state.system_offline = True
        st.rerun()
    if col2.button("아니요 (NO)", use_container_width=True):
        st.rerun()

col_left, col_center, col_right = st.columns([1, 10, 1])
with col_center:
    st.markdown("<div class='main-title'>EDGE SAVER</div>", unsafe_allow_html=True)
with col_right:
    t_col1, t_col2 = st.columns([1, 1])
    with t_col1:
        theme_icon = "☀️" if st.session_state.theme == "dark" else "🌙"
        if st.button(theme_icon, help="다크/라이트 모드 전환"):
            st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"
            st.rerun()
    with t_col2:
        if st.button("⏻", help="시스템 전원 종료"):
            shutdown_modal()

st.divider() 

col_left, col_right = st.columns([1.3, 1], gap="large")

# --- [좌측 구역] ---
with col_left:
    st.markdown("<div class='sub-title'>📷 실시간 카메라 영상</div>", unsafe_allow_html=True)
    
    frame = cctv_service.latest_frame
    fire_detected = False
    
    if frame is not None:
        cv2.imwrite(config.CAPTURE_PATH, frame)
        analysis = fire_detector.detect_fire(config.CAPTURE_PATH)
        fire_detected = analysis['fire_detected']
        st.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), width=800)
      
        alert_space = st.empty()
        if fire_detected:
            alert_space.error(f"🚨 [화재 탐지됨] {analysis['description']}")
        else:
            alert_space.empty() 
    else:
        st.info("카메라 스트리밍 연결 대기 중...")
    
    st.markdown("---")
    
    toggle_col, badge_col, _ = st.columns([2.5, 1.5, 6])
    with toggle_col:
        st.toggle("🎙️ 음성 브리핑", key="stt_toggle")
    
    with badge_col:
        badge_space = st.empty()
        if st.session_state.get('stt_toggle', False):
            badge_space.markdown("<div class='live-badge'>🟩 LIVE</div>", unsafe_allow_html=True)
        else:
            badge_space.empty()

    st.markdown("<div class='ai-sub-title'>🤖 AI 지침</div>", unsafe_allow_html=True)
    
    if st.session_state.get('is_generating', False):
        ai_text = "⚠️ AI가 위급 상황을 분석하여 지침을 생성하고 있습니다... ⏳"
    else:
        ai_text = st.session_state.last_answer if st.session_state.last_answer else "안전 상태 유지 중입니다. (지침 대기 중)"
    
    st.markdown(f"<div class='ai-box'>\n\n{ai_text}\n\n</div>", unsafe_allow_html=True)
# --- [우측 구역] ---
with col_right:
    st.markdown(f"""
        <div class='indicator-bar'>
            <div class='status-item'><span class='dot-green'></span> CAM LIVE</div>
            <div class='status-item'><span class='dot-green'></span> SENSORS</div>
            <div class='status-item'><span class='dot-green'></span> AI READY</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-title'>📊 센서 현황</div>", unsafe_allow_html=True)
    
    s_val = smoke.read_smoke_level(simulate=True)
    g_val = gas.read_gas_level(simulate=True)
    t_data = temperature.read_temperature(simulate=True)
    
    m1, m2, m3 = st.columns(3)
    m1.metric("🌡️ 온도", f"{t_data['temperature']} °C")
    m2.metric("💨 가스", f"{g_val} ppm")  
    m3.metric("🌫️ 연기", f"{s_val} %")    
    
    st.divider()
    st.markdown("<div class='sub-title'>🚨 위험도 게이지</div>", unsafe_allow_html=True)
    
    risk = fusion.calculate_risk_level(s_val, g_val, t_data, fire_detected)
    level = risk['level']
    gauge_colors = ["#28a745", "#a4c639", "#ffa500", "#ff4b4b", "#8b0000"]
    current_color = gauge_colors[level-1] if level > 0 else "#22c55e"
    
    st.markdown(f"""
        <div class="gauge-container">
            <div style="width: {level * 20}%; background-color: {current_color}; height: 22px; border-radius: 8px; transition: width 0.5s ease-in-out;"></div>
        </div>
        <p style="text-align: right; font-weight: bold; font-size: 13px; color: {current_color};">LEVEL {level} : {risk['label']}</p>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # ==========================================
    # 🚨 AI 대응 및 방송 로직 (우측 구역 백그라운드 처리)
    if level >= 4 and st.session_state.is_first_alert:
        if not st.session_state.get('is_generating', False):
            st.session_state.is_generating = True
            current_zone = getattr(config, 'ZONE_NAME', "A구역 센서노드_01")
            sensor_info = f"온도:{t_data['temperature']}°C / 가스:{g_val} / 연기:{s_val}"
            
            add_log(f"🚨 위급상황 감지! RAG 지침 생성 시작 (화면 유지 중...)")
            trigger_alarm(level, risk['details']) 
            
            def generate_emergency():
                try:
                    if tts_helper: tts_helper.stop() 
                    prompt = f"경고: 공장 내 센서와 CCTV 융합 교차 검증 결과, 심각한 화재 재난 위험(LV.{level})이 확정 감지되었습니다. (원인: {risk['details']}). 이 위급 상황에 맞는 뼈대가 되는 핵심 대피 지시 사항을 방송용으로 가장 짧고 강하게 생성해줘."
                    res = qa.invoke(prompt) 
                    st.session_state.last_answer = res['result']
                    send_alert(zone=current_zone, risk_level=level, sensor_details=sensor_info, ai_guidance=st.session_state.last_answer)
                    add_log("📢 [음성 경보] 지침 생성 완료. TTS 방송을 시작합니다...")
                    tts_helper.speak(f"비상 상황 발생! {st.session_state.last_answer}", lang='ko')
                except Exception as e:
                    add_log(f"❌ 비상 방송 시스템 오류: {e}")
                    st.session_state.is_first_alert = True
                finally:
                    st.session_state.is_first_alert = False
                    st.session_state.is_generating = False
            
            llm_thread = threading.Thread(target=generate_emergency, daemon=True)
            add_script_run_ctx(llm_thread)
            llm_thread.start()

    elif level < 4:
        st.session_state.is_first_alert = True 

    # 음성 질의 처리 (Queue)
    try:
        query = st.session_state.speech_queue.get_nowait()
        if query:
            d_lang = detect_lang(query)
            add_log(f"🎤 질의 수신({d_lang}): {query}")
            
            if not st.session_state.get('is_generating', False):
                st.session_state.is_generating = True
                add_log("⚙️ AI가 질의에 대한 답변을 생성 중입니다...")
                
                def process_query():
                    try:
                        res = qa.invoke(query)
                        st.session_state.last_answer = res['result']
                        tts_helper.speak(res['result'], lang=d_lang)
                    finally:
                        st.session_state.is_generating = False
                
                q_thread = threading.Thread(target=process_query, daemon=True)
                add_script_run_ctx(q_thread)
                q_thread.start()
                
                st.rerun()
            else:
                add_log("⚠️ [시스템] 현재 AI가 다른 작업을 처리 중입니다. 잠시 후 말씀해주세요.")
    except queue.Empty: pass

    st.markdown("<div class='sub-title'>📟 Tactical Feed</div>", unsafe_allow_html=True)
    log_text = "\n".join(list(st.session_state.system_logs)[::-1])
    st.markdown(f"<div class='log-box'>{log_text}</div>", unsafe_allow_html=True)

time.sleep(0.5)
st.rerun()
