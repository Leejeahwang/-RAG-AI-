import sys
import os
import platform

# Windows에서 심볼릭 링크 권한 에러(WinError 1314) 방지 (HuggingFace 관련)
if platform.system() == "Windows":
    os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

import threading
import time
import re
import cv2
import warnings
import logging

# 모든 라이브러리 경고 및 로그 강제 억제 (UI 보호용)
warnings.filterwarnings("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["OPENVINO_LOG_LEVEL"] = "0"
os.environ["OPENVINO_WARNINGS"] = "0"
os.environ["OV_LOGGER_LEVEL"] = "0"

# Transformers 전용 로거 설정 (이미 로드되었을 가능성 대비)
try:
    import transformers
    transformers.logging.set_verbosity_error()
except:
    pass

logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("torch").setLevel(logging.ERROR)
logging.getLogger("ultralytics").setLevel(logging.ERROR)

# [v30] Native Stack Imports
from voice.tts import TTSHelper  # [v46] 다시 표준 TTSHelper(pyttsx3)로 복구
# from voice.piper_helper import PiperTTSHelper # [DELETE]
from rag.native_retriever import rag_manager

import config
from vision import cctv_service, fire_detector
from sensors import fusion
from sensors.temperature import read_temperature, is_temperature_abnormal
from sensors.smoke import read_smoke_level, is_smoke_detected
from sensors.gas import read_gas_level, is_gas_detected
from alerts.alarm import trigger_alarm
from alerts.notifier import send_alert
# STT 모듈 임포트 시도 (pyaudio 누락 시 안전 조치)
STT_AVAILABLE = True
try:
    from voice.stt import _load_model, listen_once, _get_pyaudio_instance, _open_stream
except ImportError:
    STT_AVAILABLE = False

# UI 고도화를 위한 prompt_toolkit 추가
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class EdgeSaver:
    """엣지 세이버 통합 애플리케이션 (Prompt-Toolkit 하단 툴바 UI 적용)"""

    def __init__(self):
        self.main_llm = None
        self._initialized = False
        self._monitor_running = False
        self._monitor_thread = None
        
        # 음성 자원 (지연 로드용)
        self._tts = None
        self._stt_model = None
        self._pa = None
        self._stt_stream = None
        
        # UI 세션 및 실시간 상태 (여기에 있어야 함)
        self.session = PromptSession()
        self.current_risk_stats = "시스템 초기화 중..."
        self.current_level = 0  # 단계별 발화 속도 조절을 위한 상태 저장
        self._interrupt_generation = False
        
        # 주기적 대피 방송 루프용 전역 캐시 변수
        self._cached_evac_guidance = ""
        self._evac_broadcast_thread = None
        self._evac_broadcast_running = False

    @property
    def tts(self):
        """TTS 엔진 지연 로딩"""
        if self._tts is None:
            print("[시스템] 🔊 음성 출력(TTS) 엔진 로드 중...")
            self._tts = TTSHelper()  # [v46] 다시 표준 TTSHelper(pyttsx3)로 복구
        return self._tts

    @property
    def stt_model(self):
        """STT 모델 지연 로딩"""
        if self._stt_model is None:
            if not STT_AVAILABLE:
                return None
            print("[시스템] 🎤 음성 인식(STT) 모델 로드 중...")
            from voice.stt import _load_model
            self._stt_model = _load_model()
        return self._stt_model

    @property
    def pa(self):
        """PyAudio 인스턴스 지연 로딩"""
        if self._pa is None:
            if not STT_AVAILABLE:
                return None
            from voice.stt import _get_pyaudio_instance
            self._pa = _get_pyaudio_instance()
        return self._pa

    @property
    def stt_stream(self):
        """STT 스트림 지연 로딩"""
        if self._stt_stream is None:
            if not STT_AVAILABLE:
                return None
            from voice.stt import _open_stream
            self._stt_stream = _open_stream(self.pa)
        return self._stt_stream

    def initialize(self):
        """시스템 초기화: 밸런스 RAG 엔진 + 비전 AI + 음성 엔진 로드"""
        print("=" * 55)
        print("🔥 엣지 세이버 (Edge Saver) 통합 시스템 시작 🔥")
        print("=" * 55 + "\n")

        try:
            # ── 0단계: 지식베이스 준비 ──
            print("[시스템] 지식베이스 검색 엔진 로드 중...")

            # ── 1단계: Native RAG 데이터 로드 [v30] ──
            from rag.native_retriever import rag_manager
            from rag.loader import load_and_split
            
            rag_manager.load_resources()
            if not rag_manager.index:
                chunks = load_and_split()
                rag_manager.build_index(chunks)
            
            # ── 2단계: 음성 엔진 및 보조 모듈 로드 ──
            import contextlib
            import io

            # TTS 엔진 로드
            print("[시스템] 🔊 음성 출력(TTS) 엔진 준비 중...", end=" ", flush=True)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                _ = self.tts
            print("완료")

            # STT 엔진 로드
            if getattr(config, 'STT_ENABLED', True) and STT_AVAILABLE:
                print("[시스템] 🎤 음성 인식(STT) 엔진 준비 중...", end=" ", flush=True)
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    _ = self.stt_model
                    stream = self.stt_stream
                
                if stream is None:
                    print("⚠️  (마이크 미감지 - 텍스트 전용 모드)")
                else:
                    print("완료")
            else:
                print("[시스템] 🎤 음성 인식(STT) 기능이 비활성화되었습니다. (텍스트 모드)")

            print("[시스템] 🔊 음성 출력(TTS) 모델 예열 중...", end=" ", flush=True)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.tts.warmup()
            print("완료")

            # 백그라운드 카메라 서비스 가동
            if not cctv_service.camera_running:
                cctv_service.camera_running = True
            threading.Thread(target=cctv_service.camera_worker_thread, daemon=True).start()

            self._initialized = True
            print("\n🚀 시스템 모든 모듈 초기화 완료!\n")

        except Exception:
            import traceback
            print("\n❌ 시스템 가동 중 치명적 오류 발생:")
            traceback.print_exc()
            sys.exit(1)

    def _get_bottom_toolbar(self):
        """실시간 센서 정보를 하단 툴바 스타일(HTML)로 반환"""
        return HTML(f'<style bg="ansiblue" fg="white"> [EDGE SAVER] | {self.current_risk_stats} </style>')

    def _run_evac_broadcast(self):
        """대피 상황이 지속되는 동안 주기적으로 대피 지침을 무한 반복 방송하는 스레드"""
        print("\n📢 [시스템] 주기적 비상 대피 방송 스레드가 시작되었습니다.")
        # 방송 주기 (초)
        BROADCAST_INTERVAL = 25
        # 초기 대피 안내 발화가 끝난 뒤부터 주기를 계산할 수 있도록 시작 시점을 현재 시간으로 초기화
        last_play_time = time.time()
        
        while self._evac_broadcast_running and self._monitor_running:
            try:
                now = time.time()
                if now - last_play_time >= BROADCAST_INTERVAL:
                    if self._cached_evac_guidance:
                        # 이미 음성 출력 중인 경우 겹침/끊김 방지를 위해 대기
                        if self.tts.is_speaking():
                            time.sleep(1.0)
                            continue
                        
                        speed = 1.3 if self.current_level >= 5 else 1.2
                        # 무한 대피 방송용 안내 멘트 조합
                        broadcast_text = f"비상 대피 방송입니다. {self._cached_evac_guidance}"
                        self.tts.speak_async(broadcast_text, lang='ko', speed=speed)
                        last_play_time = now
            except Exception as e:
                print(f"⚠️ [비상 방송 에러] {e}")
            time.sleep(1.0)
        print("\n📢 [시스템] 비상 대피 방송 스레드가 종료되었습니다.")

    def _trigger_rag_alert(self, prompt, sensor_info, zone_id):
        """위급 상황 시 LLM 스트리밍 추론을 생략(Bypassing)하고, 0초 만에 100% 신뢰할 수 있는 원본 대피로를 직송합니다."""
        alert_header = (
            "\n" + "!" * 55 + "\n"
            "🚨 [긴급 개입] 시스템 원본 비상 지침을 즉각 격발(Bypass)합니다.\n"
            + "!" * 55
        )
        print(alert_header)
        
        try:
            self.tts.stop()
            from rag.native_retriever import rag_manager
            
            # 위험 상황에 맞는 매뉴얼 검색
            source_docs = rag_manager.search(prompt)
            
            # 1. 현장 평면도 원문 추출
            layout_text = ""
            layout_path = os.path.join("data", f"zone_{zone_id}_layout.txt")
            if os.path.exists(layout_path):
                with open(layout_path, "r", encoding="utf-8") as f:
                    layout_text = f.read().strip()
            
            # 2. 공장 소방 매뉴얼 핵심 수칙 원본 정제 추출
            fire_protocol_text = ""
            for doc in source_docs:
                src = doc.get('source', '')
                if "factory_fire_manual" in src.lower() or "emergency" in src.lower() or "saver" in src.lower():
                    lines = doc.get('page_content', '').split('\n')
                    clean_lines = [l for l in lines if '[위치:' not in l and '[출처:' not in l and not l.strip().startswith(('###', '---'))]
                    fire_protocol_text = "\n".join(clean_lines).strip()
                    break
            
            # 만약 매뉴얼 추출이 실패한 경우 대비 기본 대피 수칙 백업
            if not fire_protocol_text:
                fire_protocol_text = (
                    "- 연기 흡입 방지를 위해 젖은 천으로 호흡기를 막으십시오.\n"
                    "- 시야 확보가 어려울 경우 벽을 짚고 한 방향으로만 이동하십시오.\n"
                    "- 정전이나 붕괴 위험이 있으므로 엘리베이터나 리프트를 절대 탑승하지 마시고 비상계단만을 이용하십시오."
                )
            
            # 3. 고속 0초 피난 안내 템플릿 결합 (하십시오체 일관 적용)
            assembled_guidance = (
                f"[공장 {zone_id}구역 화재 비상 대피 지침]\n\n"
                f"🚨 {layout_text}\n\n"
                f"📝 [공장 화재 대피 기본 수칙]\n"
                f"{fire_protocol_text}\n\n"
                f"즉시 위 수칙에 따라 신속하게 대피하십시오."
            )
            
            alert_response = (
                "\n" + "=" * 55 + "\n"
                "🔊 [AI 즉각 피난 지침 직송 (LLM Bypass)]\n"
                "-" * 55 + "\n"
                f"{assembled_guidance}\n"
                + "=" * 55 + "\n"
            )
            print(alert_response)
            
            # 대피 지침 전역 캐싱
            self._cached_evac_guidance = assembled_guidance
            
            send_alert(zone=f"관리구역_{zone_id}", risk_level=4, sensor_details=sensor_info, ai_guidance=assembled_guidance)
            self.tts.speak_async(f"비상 상황 발생! {assembled_guidance}", lang='ko')
            
            # 주기적 비상 대피 방송 스레드 가동
            if not self._evac_broadcast_running:
                self._evac_broadcast_running = True
                self._evac_broadcast_thread = threading.Thread(target=self._run_evac_broadcast, daemon=True)
                self._evac_broadcast_thread.start()
            
        except Exception as e:
            print(f"⚠️ 긴급 대피로 직송 오류: {e}")

    def _monitor_sensors(self):
        """백그라운드 센서 및 비전 감시 (툴바 수치 갱신 전용)"""
        alarm_handled = False
        while self._monitor_running:
            try:
                # 만약 일반 상황(Level 4 미만)에서 LLM이 답변을 생성 중이라면 
                # 음성 겹침과 오버헤드를 막기 위해 센서 체크를 잠시 양보합니다.
                if getattr(self, '_is_generating', False) and self.current_level < 4:
                    time.sleep(1.0)
                    continue

                temp_data = read_temperature(simulate=True)
                gas_val = read_gas_level(simulate=True)
                smoke_val = read_smoke_level(simulate=True)
                frame = cctv_service.latest_frame
                
                fire_detected = False
                fire_desc = ""
                # 카메라 하드웨어가 오프라인(더미 프레임 출력 중)인 경우에는 AI 화재 분석을 스킵하여 오발령을 원천 방지합니다.
                if frame is not None and not getattr(cctv_service, 'camera_offline', False):
                    # 잔존 파일로 인한 오작동 방지를 위해 매번 고유한 임시 파일 생성
                    import uuid
                    tmp_path = f"live_temp_monitor_{uuid.uuid4().hex[:8]}.jpg"
                    try:
                        cv2.imwrite(tmp_path, frame)
                        if os.path.exists(tmp_path):
                            analysis = fire_detector.detect_fire(tmp_path)
                            fire_detected = analysis.get('fire_detected', False)
                            fire_desc = analysis.get('description', '')
                    finally:
                        # 분석 후 임시 파일 즉시 삭제 (디스크 잔존물 제거)
                        if os.path.exists(tmp_path):
                            try:
                                os.remove(tmp_path)
                            except:
                                pass

                # [시뮬레이터 보정] 카메라가 실제 화재를 감지하면 가상 센서 수치들도 위험 임계값 이상으로 동반 급상승시켜
                # 퓨전 엔진(fusion.py)이 Level 4/5(긴급/재난) 판정을 내리도록 트리거하여 RAG 알람 개입을 유도합니다.
                if fire_detected:
                    temp_data["temperature"] = 75.0  # 고온 임계값(60) 초과
                    smoke_val = 550                  # 연기 임계값(300) 초과
                    gas_val = 600                    # 가스 임계값(400) 초과

                risk = fusion.calculate_risk_level(smoke_val, gas_val, temp_data, fire_detected)
                level = risk['level']
                self.current_level = level  # 레벨 업데이트
                
                # RAG 전송용 위험 사유 상세 정보에 구체적인 AI 진단 텍스트(감지 클래스명, 확신도) 주입
                if fire_detected and fire_desc:
                    risk['details'] += f" | {fire_desc}"

                # 툴바 데이터 갱신 (터미널 UI 깨짐 방지를 위해 이모지 대신 텍스트/표준 기호 사용)
                self.current_risk_stats = f"T: {temp_data['temperature']}C | G: {gas_val} | S: {smoke_val} | CAM: {f'[FIRE: {fire_desc}]' if fire_detected else 'SAFE'} | {risk['label']}"
                
                if level >= 4:
                    if not alarm_handled:
                        alarm_handled = True  # 중복 RAG 트리거 및 음성 겹침 방지를 위해 진입 즉시 플래그 설정
                        # 🚨 [긴급 개입] 일반 질문에 대해 음성 답변 중이었다면 즉시 강제 중단 신호 전달 및 음성 소거
                        self._interrupt_generation = True
                        self.tts.stop()
                        
                        self._is_generating = True  # 중복 RAG 트리거 및 음성 겹침 방지 방어선 구축
                        try:
                            warning_msg = (
                                f"\n\033[31;1m" + "!" * 55 + "\n"
                                f"🚨 [재난 발생] {risk['label']} (단계: {level})\n"
                                f"📝 원인: {risk['details']}\n"
                                f"{'!' * 55}\033[0m"
                            )
                            print(warning_msg)
                            
                            trigger_alarm(level, risk['details'])
                            
                            import random
                            zone_id = random.choice(["A", "B", "C"])
                            
                            # 프롬프트에 [공장 X구역]을 명시하여 native_retriever.py의 LOCATION_MAP 필터링을 강제 트리거
                            prompt = f"[공장 {zone_id}구역] 화재 위험 지수 {level}단계 격상 ({risk['details']}). 인명 피해 방지를 위한 가장 짧고 강력한 대피 지침을 생성해줘."
                            self._trigger_rag_alert(prompt, risk['details'], zone_id)
                        finally:
                            self._is_generating = False
                elif level < 2:  # 확실하게 상황이 진정(Level 1 이하)되었을 때만 핸들 플래그 해제 및 방송 종료
                    if self._evac_broadcast_running:
                        # 대피 안내 음성이 아직 출력 중인 경우, 메시지가 끝까지 재생될 수 있도록 복귀를 대기합니다.
                        if self.tts.is_speaking():
                            time.sleep(1.0)
                            continue
                        print("\n📢 [시스템] 상황이 정상으로 복귀되었습니다. 비상 대피 방송을 즉시 종료합니다.")
                        self._evac_broadcast_running = False
                        self.tts.stop()
                        self._cached_evac_guidance = ""
                    alarm_handled = False
                
            except Exception as e:
                # 무음 크래시 방지 및 예외 디버깅 로그
                print(f"\n⚠️ [센서 감시 루프 경고] {e}")
                
            time.sleep(3)

    def run(self):
        if not self._initialized: self.initialize()

        if platform.system() == "Windows":
            try:
                import msvcrt
                while msvcrt.kbhit(): msvcrt.getch()
            except: pass

        print("[대기] 🚑 엣지 세이버 통합 모드가 가동되었습니다.")
        print("       - 화면 꼬임 방지를 위한 '하단 고정 툴바 UI'가 적용되었습니다.")
        print("       - 'q' 입력 시 종료됩니다.\n")

        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._monitor_sensors, daemon=True)
        self._monitor_thread.start()

        # patch_stdout()을 사용하여 모든 출력이 툴바를 침범하지 않게 합니다.
        with patch_stdout():
            while True:
                try:
                    query = self.session.prompt(
                        "❓ 질문: ", 
                        bottom_toolbar=self._get_bottom_toolbar,
                        refresh_interval=1.0
                    ).strip()
                    
                    # 툴바 문자열이 터미널 버퍼 레이스 컨디션으로 오염 유입된 경우 정제
                    if "[EDGE SAVER]" in query or "T:" in query:
                        query = re.sub(r'\[EDGE SAVER\]\s*\|.*?(?:정상|긴급|재난|대비|주의)', '', query).strip()
                        query = re.sub(r'❓\s*질문:\s*', '', query).strip()
                        query = re.sub(r'T:\s*\d+\.?\d*C\s*\|.*', '', query).strip()
                        query = query.replace("[EDGE SAVER]", "").strip()
                        
                    if self.tts: self.tts.stop()
                    
                    if query == "" or query.lower() in ['v', 'voice']:
                        if not getattr(config, 'STT_ENABLED', True) or self.stt_stream is None:
                            print("\n⚠️ 현재 음성 인식 기능을 사용할 수 없습니다. 텍스트로 질문해 주세요.")
                            continue
                        print("\n🎤 말씀해 주세요...")
                        query, lang = listen_once(model=self.stt_model, pa=self.pa, stream=self.stt_stream)
                        if not query: continue
                        print(f"🎤 인식: {query}")
                    elif query.lower() in ['q', 'exit', 'quit']:
                        break
                    else:
                        lang = 'ko' if re.search('[가-힣]', query) else 'en'

                    print("\n[분석] 대응 지침 생성 중...")
                    start_t = time.time()
                    
                    from rag.native_retriever import rag_manager
                    from rag.chain import rewrite_query_ollama
                    
                    # [v49] LLM 기반 고속 쿼리 재작성 적용 (Query Reformulation)
                    search_query = query
                    keywords = rewrite_query_ollama(query)
                    if keywords:
                        # 원본 질문과 명사 키워드를 병합하여 하이브리드 검색 매칭률 극대화
                        search_query = f"{query} {keywords}"
                        print(f"🔍 [RAG 쿼리 보강] 추출된 검색 키워드 주입: '{keywords}'")
                        
                    source_docs = rag_manager.search(search_query)
                    
                    # LLM 앵무새 증후군 방지: 컨텍스트 내의 메타데이터 헤더([위치:], [출처:]) 텍스트 강제 삭제
                    cleaned_chunks = []
                    seen_sources = set()  # 동일 소스 파일 중복 방지 필터 (Attention Bloat 차단)
                    for doc in source_docs:
                        src = doc.get('source', '')
                        if src:
                            if src in seen_sources:
                                continue
                            seen_sources.add(src)
                            
                        lines = doc.get('page_content', '').split('\n')
                        clean_lines = [l for l in lines if '[위치:' not in l and '[출처:' not in l and not l.strip().startswith(('###', '---'))]
                        cleaned_content = "\n".join(clean_lines).strip()
                        if cleaned_content:
                            cleaned_chunks.append(cleaned_content)
                    context_text = "\n\n".join(cleaned_chunks)
                    
                    from rag.chain import SYSTEM_PROMPT
                    formatted_prompt = SYSTEM_PROMPT.format(context=context_text, question=query)
                    
                    llm = self.main_llm
                    
                    # 위험 단계에 따른 발화 속도 계산 (4단계: 1.2x, 5단계: 1.3x)
                    speed = 1.0
                    if self.current_level >= 5: speed = 1.3
                    elif self.current_level >= 4: speed = 1.2
                    
                    print("-" * 55)
                    sentence_buffer = ""
                    self._is_generating = True # [v28] 가용 자원 집중 시작
                    self._interrupt_generation = False # 인터럽트 플래그 초기화
                    
                    try:
                        from rag.chain import call_ollama_native
                        # [v35] 직접 스트리밍 호출 (/api/chat용으로 파라미터 분리)
                        for token in call_ollama_native(prompt=context_text, question=query):
                            if getattr(self, '_interrupt_generation', False):
                                print("\n\n⚠️ [경고] 재난 상황 발생으로 일반 지침 생성을 즉시 중단합니다!")
                                break
                            print(token, end="", flush=True)
                            sentence_buffer += token
                            
                            is_split_point = any(p in token for p in ".!?\n")
                            if is_split_point and "." in token:
                                if sentence_buffer.strip() and sentence_buffer.strip()[-1].isdigit():
                                    is_split_point = False
                            
                            # [v28] 번개 분할: 첫 구절은 25자만 넘어도 즉시 음성 출력
                            if not is_split_point:
                                if "," in token and len(sentence_buffer) > 15:
                                    is_split_point = True
                                elif len(sentence_buffer) > 25 and " " in token:
                                    is_split_point = True
                            
                            if is_split_point:
                                self.tts.speak_async(sentence_buffer, lang=lang, speed=speed)
                                sentence_buffer = ""
                    finally:
                        self._is_generating = False # [v28] 감시 모드 다시 활성화
                    
                    # 인터럽트되지 않은 경우에만 남은 버퍼 출력
                    if sentence_buffer.strip() and not getattr(self, '_interrupt_generation', False):
                        self.tts.speak_async(sentence_buffer, lang=lang, speed=speed)
                    
                    print(f"\n\n✅ 완료 ({time.time() - start_t:.1f}초)")
                    if source_docs:
                        sources = set(d.get('source', 'unknown_manual') for d in source_docs)
                        print(f"[참고 문헌] {sources}")
                    print("-" * 55)

                except KeyboardInterrupt: break
                except Exception as e: print(f"❌ 오류: {e}")

    def cleanup(self):
        self._monitor_running = False
        self._evac_broadcast_running = False
        print("\n[시스템] 자원을 해제 중...")
        try:
            cctv_service.camera_running = False
        except: pass

        try:
            if self._stt_stream:
                self._stt_stream.stop_stream()
                self._stt_stream.close()
            if self._pa:
                self._pa.terminate()
            if self._tts:
                self._tts.stop()
            print("✅ 모든 자원이 안전하게 해제되었습니다.")
        except Exception as e:
            print(f"⚠️ 자원 해제 중 일부 오류 발생 (무시 가능): {e}")

if __name__ == "__main__":
    app = EdgeSaver()
    try:
        app.run()
    finally:
        app.cleanup()
