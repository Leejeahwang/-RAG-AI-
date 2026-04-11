import streamlit as st  
import cv2              
import threading        
import time             
import sys              
import os               
import queue            
import re               

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)  

import config                          
from sensors import smoke, gas, temperature, fusion 
from vision import cctv_service, fire_detector    
from voice import stt, tts            
from alerts.alarm import trigger_alarm, stop_alarm 
from alerts.notifier import send_alert 

if 'system_logs' not in st.session_state:
    st.session_state.system_logs = []  

def add_log(msg):
    """지정된 메시지를 타임스탬프와 함께 로그 박스에 추가"""
    timestamp = time.strftime('%H:%M:%S')
    st.session_state.system_logs.append(f"[{timestamp}] {msg}")
    if len(st.session_state.system_logs) > 12:  
        st.session_state.system_logs.pop(0)

def detect_lang(text):
    """정규표현식을 통해 한/일/영/중 언어를 판별함"""
    if not text: return 'ko'
    if re.search('[가-힣]', text): return 'ko'      # 한국어
    if re.search('[ぁ-んァ-ヶ]', text): return 'ja'  # 일본어
    if re.search('[\u4e00-\u9fff]', text): return 'zh' # 중국어
    if re.search('[a-zA-Z]', text): return 'en'     # 영어
    return 'ko'

@st.cache_resource 
def init_tactical_engine():
    add_log("=" * 45)
    add_log("🔥 EDGE SAVER 감시 시스템 기동 시작 🔥")
    add_log("=" * 45)
    try:
        from rag.loader import load_and_split
        from rag.retriever import build_vectorstore, get_retriever
        from rag.chain import build_qa_chain

        # 단계별 로딩 로그
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
        add_log(f"❌ 초기화 실패: {e}")
        return None, None, None, None, None


qa, stt_model, pa, stream, tts_helper = init_tactical_engine()

if 'speech_queue' not in st.session_state:
    st.session_state.speech_queue = queue.Queue()  # 음성 질문 전달 바구니
if 'last_answer' not in st.session_state: st.session_state.last_answer = ""  # AI 답변 저장
if 'is_first_alert' not in st.session_state: st.session_state.is_first_alert = True # 중복 알람 방지
if 'show_shutdown_modal' not in st.session_state: st.session_state.show_shutdown_modal = False # 종료 확인창 제어

def stt_background_worker(model, pa, stream):
    """사용자가 토글을 켰을 때만 목소리를 듣고 텍스트로 변환함"""
    while True:
        if st.session_state.get('stt_active', False):
            query, _ = stt.listen_once(model=model, pa=pa, stream=stream, use_wake_word=False)
            if query:
                st.session_state.speech_queue.put(query)
        else:
            time.sleep(0.5)

if 'threads_started' not in st.session_state:
    threading.Thread(target=cctv_service.camera_worker_thread, daemon=True).start()
    threading.Thread(target=stt_background_worker, args=(stt_model, pa, stream), daemon=True).start()
    st.session_state.threads_started = True

st.set_page_config(layout="wide", page_title="EDGE SAVER", page_icon="🛡️")

# 헤더 구역: 타이틀 + 우측 상단 전원 아이콘 (⏻)
header_left, header_right = st.columns([15, 1])
with header_left:
    st.markdown("## **EDGE SAVER** ")

with header_right:
    if st.button("⏻", help="시스템 전원 종료"):
        st.session_state.show_shutdown_modal = True

# 종료 확인 모달창 구현
if st.session_state.show_shutdown_modal:
    st.markdown("---")
    st.warning("⚠️ **시스템을 완전히 종료하시겠습니까?**")
    btn_col1, btn_col2, _ = st.columns([1, 1, 10])
    if btn_col1.button("예 (YES)"):
        add_log("🔌 시스템 안전 종료...")
        stop_alarm() 
        cctv_service.camera_running = False
        try: stream.stop_stream(); stream.close(); pa.terminate(); tts_helper.stop()
        except: pass
        st.error("시스템이 종료되었습니다."); st.stop()
    if btn_col2.button("아니요 (NO)"):
        st.session_state.show_shutdown_modal = False
        st.rerun()

st.divider()

# 메인 섹션 분할: 좌(영상/제어/로그) 2.1 | 우(수치/게이지/지침) 1.0
col_left, col_right = st.columns([2.1, 1])

# --- [실시간 카메라 영상] ---
with col_left:
    st.subheader("📷 실시간 카메라 영상")
    frame = cctv_service.latest_frame
    fire_detected = False
    if frame is not None:
        cv2.imwrite(config.CAPTURE_PATH, frame)
        analysis = fire_detector.detect_fire(config.CAPTURE_PATH)
        fire_detected = analysis['fire_detected']
        st.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), use_container_width=True)
        if fire_detected:
            st.error(f"🚨 [화재 탐지됨] {analysis['description']}")
    else:
        st.info("카메라 스트리밍 연결 대기 중...")

    st.markdown("---")
    st.session_state.stt_active = st.toggle("🎙️ 음성 브리핑", value=False)
    
    if st.session_state.stt_active:
        st.success("🟢 **LIVE...**")
    
    st.markdown("📟 **Tactical Feed**")
    st.code("\n".join(st.session_state.system_logs), language="bash")

# --- [우측 구역: 분석 데이터 및 최종 지침] ---
with col_right:
    st.subheader("📊 센서 현황")
    s_val = smoke.read_smoke_level(simulate=True)
    g_val = gas.read_gas_level(simulate=True)
    t_data = temperature.read_temperature(simulate=True)
    
    m1, m2, m3 = st.columns(3)
    m1.metric("🌡️ 온도", f"{t_data['temperature']}°C")
    m2.metric("💨 가스", f"{g_val}")
    m3.metric("🌫️ 연기", f"{s_val}")
    
    st.divider()
    
    # 수평 막대형 위험도 게이지
    st.subheader("🚨 위험도 게이지")
    risk = fusion.calculate_risk_level(s_val, g_val, t_data, fire_detected)
    level = risk['level']
    
    # 위험 레벨별 색상 (진한 빨강으로 갈수록 위험)
    gauge_colors = ["#28a745", "#a4c639", "#ffa500", "#ff4b4b", "#8b0000"]
    current_color = gauge_colors[level-1]
    
    # HTML/CSS 기반 수평 게이지 구현
    st.markdown(f"""
        <div style="width: 100%; background-color: #e0e0e0; border-radius: 10px; margin-bottom: 5px;">
            <div style="width: {level * 20}%; background-color: {current_color}; height: 30px; border-radius: 10px; transition: width 0.5s ease-in-out;"></div>
        </div>
        <p style="text-align: right; font-weight: bold; color: {current_color};">LEVEL {level} : {risk['label']}</p>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # 🚨 자동 대응 및 비상 방송 로직 통합
    st.subheader("🤖 AI 지침")
    
    if (level >= 4 or fire_detected) and st.session_state.is_first_alert:
        current_zone = getattr(config, 'ZONE_NAME', "A구역 센서노드_01")
        sensor_info = f"온도:{t_data['temperature']}°C / 가스:{g_val} / 연기:{s_val}"
        
        add_log(f"🚨 위급상황 감지! RAG 지침 생성 및 비상 방송 준비")
        trigger_alarm(level, risk['details']) 
        
        try:
            if tts_helper: tts_helper.stop() 
            
            # RAG 지침 생성
            res = qa.invoke(f"위급상황 LV.{level} 발생. 원인:{risk['details']}. 짧고 명확한 피난 지침 생성.")
            ai_response = res['result']
            st.session_state.last_answer = ai_response
            
            send_alert(zone=current_zone, risk_level=level, sensor_details=sensor_info, ai_guidance=ai_response)
            
            # 비상 방송 송출
            add_log("📢 [음성 경보] TTS 비상 피난 방송을 시작합니다...")
            tts_helper.speak(f"비상 상황 발생! {ai_response}", lang='ko')
            
            st.session_state.is_first_alert = False
        except Exception as e:
            add_log(f"❌ 비상 방송 시스템 오류: {e}")

    elif level < 4 and not fire_detected:
        st.session_state.is_first_alert = True # 정상 수치로 돌아오면 알람 초기화

    # 음성 질의 처리
    try:
        query = st.session_state.speech_queue.get_nowait()
        if query:
            d_lang = detect_lang(query)
            add_log(f"🎤 질의 수신({d_lang}): {query}")
            res = qa.invoke(query)
            st.session_state.last_answer = res['result']
            tts_helper.speak(res['result'], lang=d_lang)
            st.rerun()
    except queue.Empty: pass

    if st.session_state.last_answer:
        st.info(st.session_state.last_answer)
    else:
        st.write("안전 상태 유지 중입니다.")

time.sleep(0.5)
st.rerun()