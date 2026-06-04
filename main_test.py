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

# Native Stack Imports
from voice.tts import TTSHelper  
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

class EdgeSaverTest:
    """엣지 세이버 통합 애플리케이션 (Reranker 검증 전용 - 4단계 비상 경보 개입 미작동 버전)"""

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
        
        # UI 세션 및 실시간 상태
        self.session = PromptSession()
        self.current_risk_stats = "시스템 초기화 중..."
        self.current_level = 0  
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
            self._tts = TTSHelper()  
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
        """시스템 초기화: 밸런스 BGE-Base Reranker 엔진 + 비전 AI + 음성 엔진 로드"""
        print("=" * 65)
        print("🔥 엣지 세이버 (Edge Saver) Reranker 검증용 테스트 가동 🔥")
        print("=" * 65 + "\n")

        try:
            # ── 0단계: 지식베이스 준비 ──
            print("[시스템] BGE-Base 통합 RAG 지식베이스 검색 엔진 로드 중...")

            # ── 1단계: Native RAG 데이터 로드 ──
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
            print("\n🚀 Reranker 통합 시스템 모듈 초기화 완료!\n")

        except Exception:
            import traceback
            print("\n❌ 시스템 가동 중 치명적 오류 발생:")
            traceback.print_exc()
            sys.exit(1)

    def _get_bottom_toolbar(self):
        """실시간 센서 정보를 하단 툴바 스타일(HTML)로 반환"""
        return HTML(f'<style bg="ansiblue" fg="white"> [EDGE SAVER TEST - RERANKER ACTIVE] | {self.current_risk_stats} </style>')

    def _monitor_sensors(self):
        """백그라운드 센서 및 비전 감시 (4단계 경보 격발 미작동 모드)"""
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
                if frame is not None and not getattr(cctv_service, 'camera_offline', False):
                    import uuid
                    tmp_path = f"live_temp_monitor_{uuid.uuid4().hex[:8]}.jpg"
                    try:
                        cv2.imwrite(tmp_path, frame)
                        if os.path.exists(tmp_path):
                            analysis = fire_detector.detect_fire(tmp_path)
                            fire_detected = analysis.get('fire_detected', False)
                            fire_desc = analysis.get('description', '')
                    finally:
                        if os.path.exists(tmp_path):
                            try:
                                os.remove(tmp_path)
                            except:
                                pass

                # 시뮬레이터 보정
                if fire_detected:
                    temp_data["temperature"] = 75.0  
                    smoke_val = 550                  
                    gas_val = 600                    

                risk = fusion.calculate_risk_level(smoke_val, gas_val, temp_data, fire_detected)
                level = risk['level']
                self.current_level = level  
                
                if fire_detected and fire_desc:
                    risk['details'] += f" | {fire_desc}"

                # 하단 툴바 갱신
                self.current_risk_stats = f"T: {temp_data['temperature']}C | G: {gas_val} | S: {smoke_val} | CAM: {f'[FIRE: {fire_desc}]' if fire_detected else 'SAFE'} | {risk['label']}"
                
                if level >= 4:
                    # [TEST MODE] 4단계 이상 비상 경보 격발(RAG 알림 바이패스, 음성 비상 스레드)을 미작동시킵니다.
                    # Q&A 자유 테스트가 엉킴 없이 가능하게끔 1회 콘솔 인쇄 경고만 노출합니다.
                    if not alarm_handled:
                        alarm_handled = True
                        warning_msg = (
                            f"\n\033[33;1m" + "!" * 65 + "\n"
                            f"⚠️ [TEST MODE - 4단계 미작동] 센서 수치가 {risk['label']} (단계: {level})에 도달했습니다.\n"
                            f"📝 원인: {risk['details']}\n"
                            f"💡 테스트 모드이므로 비상 경보/대피 방송 강제 개입은 비활성화 상태입니다. (자유롭게 Q&A 테스트 가능)\n"
                            f"{'!' * 65}\033[0m"
                        )
                        print(warning_msg)
                elif level == 0:  # 센서 및 비전 위험이 완전히 정상(Level 0)으로 소멸되었을 때만 알람 흔들림(Chattering) 방지를 위해 해제
                    alarm_handled = False
                
            except Exception as e:
                print(f"\n⚠️ [센서 감시 루프 경고] {e}")
                
            time.sleep(3)

    def run(self):
        if not self._initialized: self.initialize()

        if platform.system() == "Windows":
            try:
                import msvcrt
                while msvcrt.kbhit(): msvcrt.getch()
            except: pass

        print("[대기] 🚑 엣지 세이버 Reranker 검증용 테스트 쉘이 실행되었습니다.")
        print("       - Reranker가 결합된 RAG 지식 검색 Q&A를 자유롭게 질의하실 수 있습니다.")
        print("       - 'q' 입력 시 종료됩니다.\n")

        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._monitor_sensors, daemon=True)
        self._monitor_thread.start()

        with patch_stdout():
            while True:
                try:
                    query = self.session.prompt(
                        "❓ 질문: ", 
                        bottom_toolbar=self._get_bottom_toolbar,
                        refresh_interval=1.0
                    ).strip()
                    
                    if "[EDGE SAVER]" in query or "T:" in query:
                        query = re.sub(r'\[EDGE SAVER.*?\]\s*\|.*?(?:정상|긴급|재난|대비|주의)', '', query).strip()
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
                    
                    # [1.5B 키워드 추출 제거] 라즈베리파이5 연산 병목 제거를 위해 LLM 쿼리 재작성 레이어 제거 (원본 쿼리 직송)
                    search_query = query
                        
                    # BGE-Base Reranker가 내부적으로 자동 작동하여 상위 4개 엄선
                    source_docs = rag_manager.search(search_query)
                    
                    cleaned_chunks = []
                    seen_sources = set()  
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
                    
                    speed = 1.0
                    if self.current_level >= 5: speed = 1.3
                    elif self.current_level >= 4: speed = 1.2
                    
                    print("-" * 55)
                    sentence_buffer = ""
                    self._is_generating = True 
                    self._interrupt_generation = False 
                    
                    try:
                        from rag.chain import call_ollama_native
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
                            
                            if not is_split_point:
                                if "," in token and len(sentence_buffer) > 15:
                                    is_split_point = True
                                elif len(sentence_buffer) > 25 and " " in token:
                                    is_split_point = True
                            
                            if is_split_point:
                                self.tts.speak_async(sentence_buffer, lang=lang, speed=speed)
                                sentence_buffer = ""
                    finally:
                        self._is_generating = False 
                    
                    if sentence_buffer.strip() and not getattr(self, '_interrupt_generation', False):
                        self.tts.speak_async(sentence_buffer, lang=lang, speed=speed)
                    
                    print(f"\n\n✅ 완료 ({time.time() - start_t:.1f}초)")
                    if source_docs:
                        sources = set(d.get('source', 'unknown_manual') for d in source_docs)
                        print(f"[참고 문헌 (BGE-Base Reranker 정렬 적용)] {sources}")
                    print("-" * 55)

                except KeyboardInterrupt: break
                except Exception as e: print(f"❌ 오류: {e}")

    def cleanup(self):
        self._monitor_running = False
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
    app = EdgeSaverTest()
    try:
        app.run()
    finally:
        app.cleanup()
