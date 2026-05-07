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

# Transformers 전용 로거 설정 (이미 로드되었을 가능성 대비)
try:
    import transformers
    transformers.logging.set_verbosity_error()
except:
    pass

logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("torch").setLevel(logging.ERROR)

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
from voice.tts import TTSHelper
from voice.stt import _load_model, listen_once, _get_pyaudio_instance, _open_stream

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
            print("[시스템] 🎤 음성 인식(STT) 모델 로드 중...")
            from voice.stt import _load_model
            self._stt_model = _load_model()
        return self._stt_model

    @property
    def pa(self):
        """PyAudio 인스턴스 지연 로딩"""
        if self._pa is None:
            from voice.stt import _get_pyaudio_instance
            self._pa = _get_pyaudio_instance()
        return self._pa

    @property
    def stt_stream(self):
        """STT 스트림 지연 로딩"""
        if self._stt_stream is None:
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
            print("[시스템] 🎤 음성 인식(STT) 엔진 준비 중...", end=" ", flush=True)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                _ = self.stt_model
                _ = self.stt_stream
            print("완료")

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

    def _trigger_rag_alert(self, prompt, sensor_info):
        """위급 상황 시 콘솔 출력 (patch_stdout이 대화 본문을 자동으로 보호함)"""
        print("\n" + "!" * 55)
        print("🚨 [긴급 개입] AI가 현장 상황을 분석하여 대응 지시를 내립니다.")
        print("!" * 55)
        
        try:
            self.tts.stop()
            from rag.chain import call_ollama_native, SYSTEM_PROMPT
            from rag.native_retriever import rag_manager
            
            source_docs = rag_manager.search(prompt)
            context_text = "\n\n".join([d.get('page_content', '') for d in source_docs])
            formatted_prompt = SYSTEM_PROMPT.format(context=context_text, question=prompt)
            
            ai_response = ""
            for token in call_ollama_native(formatted_prompt):
                ai_response += token
            
            print("\n" + "=" * 55)
            print("🔊 [AI 긴급 피난 안내]")
            print("-" * 55)
            print(f"{ai_response}")
            print("=" * 55 + "\n")
            
            send_alert(zone="관리구역_01", risk_level=4, sensor_details=sensor_info, ai_guidance=ai_response)
            self.tts.speak_async(f"비상 상황 발생! {ai_response}", lang='ko')
            
        except Exception as e:
            print(f"⚠️ 긴급 RAG 생성 오류: {e}")

    def _monitor_sensors(self):
        """백그라운드 센서 및 비전 감시 (툴바 수치 갱신 전용)"""
        alarm_handled = False
        while self._monitor_running:
            try:
                temp_data = read_temperature(simulate=True)
                gas_val = read_gas_level(simulate=True)
                smoke_val = read_smoke_level(simulate=True)
                frame = cctv_service.latest_frame
                
                fire_detected = False
                if frame is not None:
                    tmp_path = "live_temp_main.jpg"
                    cv2.imwrite(tmp_path, frame)
                    analysis = fire_detector.detect_fire(tmp_path)
                    fire_detected = analysis.get('fire_detected', False)

                risk = fusion.calculate_risk_level(smoke_val, gas_val, temp_data, fire_detected)
                level = risk['level']
                self.current_level = level  # 레벨 업데이트
                
                # 툴바 데이터 갱신 (터미널 UI 깨짐 방지를 위해 이모지 대신 텍스트/표준 기호 사용)
                self.current_risk_stats = f"T: {temp_data['temperature']}C | G: {gas_val} | S: {smoke_val} | CAM: {'[FIRE]' if fire_detected else 'SAFE'} | {risk['label']}"
                
                if level >= 4 and not alarm_handled:
                    # ... (rest of the logic remains)
                    print(f"\n\033[31;1m" + "!" * 55)
                    print(f"🚨 [재난 발생] {risk['label']} (단계: {level})")
                    print(f"📝 원인: {risk['details']}")
                    print("!" * 55 + "\033[0m")
                    
                    trigger_alarm(level, risk['details'])
                    prompt = f"화재 위험 지수 4단계 격상 ({risk['details']}). 인명 피해 방지를 위한 가장 짧고 강력한 대피 지침을 생성해줘."
                    self._trigger_rag_alert(prompt, risk['details'])
                    alarm_handled = True
                elif level < 1:
                    alarm_handled = False
                
                time.sleep(3)
            except:
                pass

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
                    
                    if self.tts: self.tts.stop()
                    
                    if query == "" or query.lower() in ['v', 'voice']:
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
                    source_docs = rag_manager.search(query)
                    
                    # LLM 앵무새 증후군 방지: 컨텍스트 내의 메타데이터 헤더([위치:], [출처:]) 텍스트 강제 삭제
                    cleaned_chunks = []
                    for doc in source_docs:
                        lines = doc.get('page_content', '').split('\n')
                        clean_lines = [l for l in lines if '[위치:' not in l and '[출처:' not in l and not l.strip().startswith(('###', '---'))]
                        cleaned_chunks.append("\n".join(clean_lines))
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
                    
                    try:
                        from rag.chain import call_ollama_native
                        # [v35] 직접 스트리밍 호출
                        for token in call_ollama_native(formatted_prompt):
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
                    
                    if sentence_buffer.strip():
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
