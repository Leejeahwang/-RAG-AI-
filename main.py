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
from voice.tts import TTSHelper
from voice.stt import _load_model, listen_once, _get_pyaudio_instance, _open_stream


class EdgeSaver:
    """엣지 세이버 메인 애플리케이션"""

    def __init__(self):
        self.qa = None
        self._initialized = False
        
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

    def run(self):
        """전체 감시 파이프라인 실행 (음성 모드 포함)"""
        if not self._initialized:
            raise RuntimeError("initialize()를 먼저 호출하세요.")

        # [버그 수정] 시작 시 터미널 버퍼에 남아있는 엔터 키 등을 비웁니다 (Windows 전용)
        if platform.system() == "Windows":
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getch()
        
        print("[대기] 🚑 엣지 세이버(Edge Saver)가 가동되었습니다.")
        print("       - 직접 질문을 입력하거나,")
        print("       - [엔터]를 치면 음성 인식을 시작합니다.")
        print("       - 종료하려면 'q' 또는 'exit'를 입력하세요.\n")

        while True:
            try:
                # 87-88라인의 잘못된 위치(루프 상단)에서 tts.stop()을 제거했습니다.
                
                query = input("❓ 질문 (텍스트 입력 또는 '엔터'로 음성 모드): ").strip()
                
                # 사용자가 엔터를 누르는 순간(입력 완료) 기존 음성 안내를 중단합니다.
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
                
                # [강력 조치] 언어 이탈 방지용 힌트는 프롬프트 단계로 수관하고, 여기선 순수 쿼리만 전달
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

    def cleanup(self):
        """시스템 종료 시 자원 해제"""
        print("\n[시스템] 자원을 해제하는 중...")
        try:
            if self.stt_stream:
                self.stt_stream.stop_stream()
                self.stt_stream.close()
            if self.pa:
                self.pa.terminate()
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
