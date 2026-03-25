"""
🚑 엣지 세이버 (Edge Saver) - 파이프라인 테스트
Vision AI → RAG 검색을 하나의 흐름으로 테스트합니다.

사용법:
    python main.py
    python main.py test.png    (이미지 파일을 지정할 경우)
"""

import sys
import os
import random

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from rag.loader import load_and_split
from rag.retriever import build_vectorstore, get_retriever
from rag.chain import build_qa_chain

# ──────────────────────────────────────────────
# Vision AI 구현 전까지 사용할 시뮬레이션 시나리오
# ──────────────────────────────────────────────
SIMULATION_SCENARIOS = [
    "출혈이 심한 환자가 쓰러져 있습니다. 지혈 방법을 알려주세요.",
    "환자가 의식이 없고 호흡이 없습니다. 심폐소생술 방법을 알려주세요.",
    "높은 곳에서 추락하여 다리가 부러진 것 같습니다. 골절 응급처치 방법을 알려주세요.",
    "건물에서 화재가 발생했습니다. 대피 방법을 알려주세요.",
    "산에서 길을 잃었습니다. 어떻게 해야 하나요?",
]


class EdgeSaverApp:
    """엣지 세이버 메인 애플리케이션"""

    def __init__(self):
        self.qa = None
        self._initialized = False

    def initialize(self) -> None:
        """
        전체 시스템을 초기화합니다.
        - 매뉴얼 데이터 로딩 & 청킹
        - 벡터DB 구축
        - QA 체인 구성
        """
        print("=" * 50)
        print("🚑 엣지 세이버 (Edge Saver) 시스템 초기화 중... 🚑")
        print("=" * 50 + "\n")

        try:
            # 1) 매뉴얼 데이터 로딩 & 청킹
            print("[시스템] 1/3: 매뉴얼 데이터 로딩...")
            chunks = load_and_split()

            # 2) 벡터DB 생성
            print("[시스템] 2/3: 벡터DB 구축 중...")
            db = build_vectorstore(chunks)
            retriever = get_retriever(db)

            # 3) QA 체인 구성
            print("[시스템] 3/3: QA 체인 구성 중...")
            self.qa = build_qa_chain(retriever)

        except ConnectionError:
            print("\n❌ Ollama 서버에 연결할 수 없습니다!")
            print("   → Ollama가 실행 중인지 확인하세요: https://ollama.com")
            print(f"   → 모델이 설치되어 있는지 확인하세요: ollama pull {config.LLM_MODEL}")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ 초기화 중 오류 발생: {e}")
            print("   → Ollama가 실행 중인지 확인하세요: https://ollama.com")
            print(f"   → 모델 확인: ollama pull {config.LLM_MODEL}")
            sys.exit(1)

        self._initialized = True
        print("\n✅ 시스템 초기화 완료!\n")

    def analyze_image(self, image_path: str) -> str:
        """
        Vision AI로 이미지를 분석하여 상황 키워드를 추출합니다.

        Args:
            image_path: 분석할 이미지 파일 경로

        Returns:
            추출된 상황 설명 문자열

        TODO (규태님):
            vision/camera.py의 capture_frame()과 연동하여
            실제 Vision AI(LLaVA) 분석 결과를 반환하도록 구현
        """
        if not os.path.exists(image_path):
            print(f"⚠️ 이미지 파일을 찾을 수 없습니다: {image_path}")
            print("   → 시뮬레이션 모드로 전환합니다.\n")
            scenario = random.choice(SIMULATION_SCENARIOS)
            return scenario

        # TODO: 실제 Vision AI 연동 시 아래 코드를 교체
        print(f"📷 이미지 분석 중: {image_path}")
        scenario = random.choice(SIMULATION_SCENARIOS)
        return scenario

    def run(self, image_path: str = None) -> None:
        """
        전체 파이프라인을 실행합니다.
        이미지 → Vision AI (상황 분석) → RAG 검색 → AI 답변

        Args:
            image_path: 분석할 이미지 파일 경로 (없으면 시뮬레이션)
        """
        if not self._initialized:
            raise RuntimeError("시스템이 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")

        # ── Step 1: Vision AI로 상황 분석 ──
        print("[분석] Vision AI에게 사진 분석을 요청합니다...")
        if image_path:
            query = self.analyze_image(image_path)
        else:
            query = random.choice(SIMULATION_SCENARIOS)
            print("📷 이미지 없음 → 시뮬레이션 질문 사용\n")

        print(f"👁️‍🗨️ [Vision AI 분석 결과]: {query}\n")

        # ── Step 2: RAG + LLM으로 답변 생성 ──
        print("[검색] 매뉴얼에서 관련 내용을 검색하고 답변을 생성합니다...")
        try:
            result = self.qa.invoke(query)

            print("\n" + "=" * 50)
            print("🚨 [최종 결과: 응급처치 지침] 🚨")
            print("=" * 50)
            print(f"\n🤖 AI 답변: {result['result']}\n")
            print("=" * 50)

        except Exception as e:
            print(f"❌ 오류가 발생했습니다: {e}")


def main():
    """CLI 진입점"""
    # 명령줄 인수로 이미지 경로를 받을 수 있음
    image_path = sys.argv[1] if len(sys.argv) > 1 else None

    app = EdgeSaverApp()
    app.initialize()
    app.run(image_path)


if __name__ == "__main__":
    main()
