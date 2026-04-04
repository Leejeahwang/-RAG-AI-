"""
🔥 엣지 세이버 (Edge Saver) — 메인 진입점

센서 감지 → Vision AI 분석 → RAG 검색 → LLM 대응 지침 생성 → 알림/음성 출력
전체 파이프라인을 조립하고 실행합니다.

사용법:
    python main.py
"""

import sys
import os
import platform
import threading
import time
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from sensors.temperature import read_temperature, is_temperature_abnormal
from alerts.alarm import trigger_alarm
from alerts.notifier import send_alert
from voice.tts import TTSHelper
from voice.stt import _load_model, listen_once, _get_pyaudio_instance, _open_stream

class EdgeSaver:
    """엣지 세이버 메인 애플리케이션"""

    def __init__(self):
        self.qa = None
        self._initialized = False
        self._monitor_running = False
        self._monitor_thread = None
        
        # 음성 자원 (STT/TTS)
        self.tts = None
        self.stt_model = None
        self.pa = None
        self.stt_stream = None

    def initialize(self):
        """시스템 초기화: RAG DB 구축 + QA 체인 구성"""
        print("=" * 55)
        print("🔥 엣지 세이버 (Edge Saver) 화재 감시 시스템 시작 🔥")
        print("=" * 55 + "\n")

        try:
            from rag.loader import load_and_split
            from rag.retriever import build_vectorstore, get_retriever
            from rag.chain import build_qa_chain

            print("[시스템] 1/3: 소방 매뉴얼 로딩...")
            chunks = load_and_split()

            print("[시스템] 2/3: 벡터DB 구축...")
            db = build_vectorstore(chunks)
            retriever = get_retriever(db)

            print("[시스템] 3/3: LLM QA 체인 구성...")
            self.qa = build_qa_chain(retriever)

            # --- 음성 엔진 추가 초기화 ---
            print("[시스템] + 음성 출력(TTS) 엔진 준비 중...")
            self.tts = TTSHelper()

            print("[시스템] + 음성 인식(STT) 엔진 준비 중...")
            self.stt_model = _load_model()
            self.pa = _get_pyaudio_instance()
            self.stt_stream = _open_stream(self.pa)

            self._initialized = True
            print("\n✅ 시스템 모든 모듈 초기화 완료!\n")

        except Exception as e:
            print(f"\n❌ 초기화 실패: {e}")
            print(f"   → Ollama 실행 확인: https://ollama.com")
            print(f"   → 모델 확인: ollama pull {config.LLM_MODEL}")
            sys.exit(1)

    def _detect_lang(self, text):
        """텍스트의 주 사용 언어를 간단히 판별"""
        if not text: return 'ko'
        # 한글 포함 시 한국어
        if re.search('[가-힣]', text): return 'ko'
        # 일어 포함 시 일본어
        if re.search('[ぁ-んァ-ヶ]', text): return 'ja'
        # 한자 포함 시 중국어 (한국/일어 제외 후)
        if re.search('[\u4e00-\u9fff]', text): return 'zh'
        # 영어 알파벳 포함 시 영어
        if re.search('[a-zA-Z]', text): return 'en'
        # 기본값 한국어
        return 'ko'

    def start_sensor_monitoring(self):
        """백그라운드에서 센서 데이터를 주기적으로 검사합니다."""
        def monitor():
            print("[모니터링] 🌡️ 온도 센서 백그라운드 감시 시작 (3초 주기)...")
            alarm_handled = False
            while self._monitor_running:
                data = read_temperature(simulate=True)
                # 실시간 측정값 출력
                print(f"  > [센서] 현재 온도: {data['temperature']}°C / 습도: {data['humidity']}%")
                
                if is_temperature_abnormal(data):
                    if not alarm_handled:
                        trigger_alarm(3, f"고온 감지! 현재 온도: {data['temperature']}°C")
                        print(f"\n🚨 [위험 감지] 온도 {data['temperature']}°C 초과! RAG 시스템 개입 시작...")
                        
                        prompt = f"경고: 공장 내 온도가 {data['temperature']}도로 비정상적으로 높습니다. 산업용 화재 매뉴얼에 따른 즉각적인 초기 대응 요령은 무엇입니까?"
                        print(f"   > 질의 생성: {prompt}")
                        try:
                            # 기존 음성 중단
                            if self.tts:
                                self.tts.stop()
                                
                            # 백그라운드 스레드에서 RAG 호출
                            result = self.qa.invoke(prompt)
                            ai_response = result['result']
                            
                            print("\n" + "=" * 55)
                            print("🔥 [AI 자동 생성: 긴급 대응 지침] 🔥")
                            print("=" * 55)
                            print(f"\n{ai_response}\n")
                            print("=" * 55 + "\n")
                            
                            # 관제실로 알림 전송 (MQTT)
                            sensor_info = f"온도 {data['temperature']}°C / 습도 {data['humidity']}%"
                            send_alert(zone="A구역 센서노드_01", risk_level=3, sensor_details=sensor_info, ai_guidance=ai_response)
                            
                            # 현장 스피커 비상 방송 (TTS)
                            print("   📢 [음성 경보] TTS 비상 피난 방송을 시작합니다...")
                            self.tts.speak_async(f"비상 상황 발생! {ai_response}", lang='ko')
                            
                        except Exception as e:
                            print(f"\n❌ RAG 생성 실패: {e}\n")
                        
                        alarm_handled = True
                else:
                    alarm_handled = False
                    
                time.sleep(3)

        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=monitor, daemon=True)
        self._monitor_thread.start()

    def run(self):
        """전체 감시 파이프라인 실행 (음성 모드 포함)"""
        if not self._initialized:
            raise RuntimeError("initialize()를 먼저 호출하세요.")

        # 시작 시 터미널 버퍼에 남아있는 엔터 키 등을 비웁니다 (Windows 전용)
        if platform.system() == "Windows":
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getch()

        print("[대기] 🚑 엣지 세이버(Edge Saver)가 가동되었습니다.")
        print("       - 직접 질문을 입력하거나,")
        print("       - [엔터]를 치면 음성 인식을 시작합니다.")
        print("       - 종료하려면 'q' 또는 'exit'를 입력하세요.\n")

        # 백그라운드 온도 감시 스레드 시작 (사용자 요청으로 임시 중단)
        # self.start_sensor_monitoring()

        while True:
            try:
                query = input("❓ 질문 (텍스트 입력 또는 '엔터'로 음성 모드): ").strip()
                
                # 사용자가 엔터를 누르는 순간(입력 완료) 기존 음성 안내를 중단합니다.
                if self.tts:
                    self.tts.stop()
                
                # 음성 인식 모드 진입
                lang = 'ko'
                if query == "" or query.lower() in ['v', 'voice', '음성']:
                    print("\n🎤 음성 인식 모드입니다. 바로 말씀해 주세요.")
                    query, lang = listen_once(model=self.stt_model, pa=self.pa, stream=self.stt_stream, use_wake_word=False)
                    
                    if not query:
                        print("⚠️ 음성이 인식되지 않았습니다. 다시 시도해 주세요.")
                        continue
                    print(f"🎤 인식된 질문 ({lang}): {query}")
                else:
                    # 텍스트 입력 시 언어 판별
                    lang = self._detect_lang(query)

                if query.lower() in ['q', 'exit', 'quit', '종료']:
                    print("\n시스템을 종료합니다.")
                    break
                
                print("\n[검색] 대응 지침 생성 중...")
                result = self.qa.invoke(query)
                answer = result['result']

                print("\n" + "=" * 55)
                print("🚨 [대응 지침]")
                print("=" * 55)
                print(f"\n{answer}\n")
                print("=" * 55 + "\n")

                # TTS 음성 출력 (감지된 언어에 맞게 출력)
                self.tts.speak_async(answer, lang=lang)

            except KeyboardInterrupt:
                print("\n\n사용자에 의해 시스템이 중단되었습니다.")
                break
            except Exception as e:
                print(f"❌ 오류: {e}\n")
        
        self._monitor_running = False

    def cleanup(self):
        """시스템 종료 시 자원 해제"""
        print("\n[시스템] 자원을 해제하는 중...")
        try:
            if self.stt_stream:
                self.stt_stream.stop_stream()
                self.stt_stream.close()
            if self.pa:
                self.pa.terminate()
            if self.tts:
                self.tts.stop()
            print("✅ 모든 자원이 안전하게 해제되었습니다.")
        except Exception as e:
            print(f"⚠️ 자원 해제 중 오류 발생: {e}")

if __name__ == "__main__":
    app = EdgeSaver()
    try:
        app.initialize()
        app.run()
    finally:
        app.cleanup()
