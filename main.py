"""
🚑 엣지 세이버(Edge Saver) — 통합 진입점

사용법:
    python main.py
"""

from rag.loader import load_and_split
from rag.retriever import build_vectorstore, get_retriever
from rag.chain import build_qa_chain


def main():
    # ── 1. 매뉴얼 데이터 로딩 & 청킹 ──
    print("📦 엣지 세이버 매뉴얼 데이터를 분석 중입니다...")
    chunks = load_and_split()

    # ── 2. 벡터DB 생성 ──
    db = build_vectorstore(chunks)
    retriever = get_retriever(db)

    # ── 3. QA 체인 구성 ──
    qa = build_qa_chain(retriever)

    # ── 4. 대화형 루프 ──
    print("\n" + "=" * 50)
    print("🚑 엣지 세이버(Edge Saver)가 실행되었습니다.")
    print("   질문을 입력하세요. (종료하려면 '종료' 또는 'exit' 입력)")
    print("=" * 50 + "\n")

    while True:
        query = input("❓ 질문: ")

        if query.strip() in ["종료", "exit", "quit"]:
            print("👋 안전을 기원합니다. 시스템을 종료합니다.")
            break

        if not query.strip():
            continue

        print("🔍 답변 생성 중...")
        try:
            result = qa.invoke(query)
            print(f"\n🤖 AI 답변: {result['result']}\n")
            print("-" * 30)
        except Exception as e:
            print(f"❌ 오류가 발생했습니다: {e}")


if __name__ == "__main__":
    main()
