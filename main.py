"""
🔥 엣지 세이버 (Edge Saver) — 메인 진입점

센서 감지 → Vision AI 분석 → RAG 검색 → LLM 대응 지침 생성 → 알림/음성 출력
전체 파이프라인을 조립하고 실행합니다.

사용법:
    python main.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config


class EdgeSaver:
    """엣지 세이버 메인 애플리케이션"""

    def __init__(self):
        self.qa = None
        self._initialized = False

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

            self._initialized = True
            print("\n✅ 시스템 초기화 완료!\n")

        except Exception as e:
            print(f"\n❌ 초기화 실패: {e}")
            print(f"   → Ollama 실행 확인: https://ollama.com")
            print(f"   → 모델 확인: ollama pull {config.LLM_MODEL}")
            sys.exit(1)

    def run(self):
        """
        전체 감시 파이프라인 실행

        TODO (전체):
            Phase 1에서는 각 모듈을 개별 테스트합니다.
            Phase 2에서 아래 루프를 완성하여 통합합니다.

            while True:
                1. sensors/ → 센서 데이터 수집
                2. 임계값 초과 시 → vision/ → 카메라 촬영 + AI 분석
                3. 오경보 필터링 (진짜 화재인지 2차 검증)
                4. 위험도 등급 산정 (Level 1~5)
                5. rag/ + LLM → 건물 맞춤 대응 지침 생성
                6. alerts/ → 경보 발령 + 관제실 알림
                7. voice/ → 음성 안내 출력
        """
        if not self._initialized:
            raise RuntimeError("initialize()를 먼저 호출하세요.")

        print("[대기] 센서 모니터링을 시작합니다...")
        print("       (현재는 시뮬레이션 모드입니다)\n")

        # 시뮬레이션: 수동 질문 입력 모드
        while True:
            try:
                query = input("🔍 시뮬레이션 질문 (종료: q): ").strip()
                if query.lower() == 'q':
                    print("\n시스템을 종료합니다.")
                    break
                if not query:
                    continue

                print("\n[검색] RAG 매뉴얼 검색 + LLM 답변 생성 중...")
                result = self.qa.invoke(query)

                print("\n" + "=" * 55)
                print("🚨 [대응 지침]")
                print("=" * 55)
                print(f"\n{result['result']}\n")
                print("=" * 55 + "\n")

            except KeyboardInterrupt:
                print("\n\n시스템을 종료합니다.")
                break
            except Exception as e:
                print(f"❌ 오류: {e}\n")


if __name__ == "__main__":
    app = EdgeSaver()
    app.initialize()
    app.run()
