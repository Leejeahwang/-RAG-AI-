"""Check relevant evidence in the top two chunks, with BGE disabled."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("NUMBA_CACHE_DIR", str(ROOT / "scratch/numba_cache"))


def main():
    import config
    config.USE_RERANKER = False
    from rag.native_retriever import NativeRAGManager
    from rag.search_intent import medical_intent
    manager = NativeRAGManager()
    manager.load_resources()
    cases = [
        ("공장 화재시 대처방법은?", "factory_fire_manual.txt", ("화재",)),
        ("아파트에서 화재가 발생하면 어떻게 대피하나요?", "(아파트 입주자) 화재 피난행동요령.pdf", ("대피", "피난")),
        ("A구역 화재시 대피방법은?", "zone_A_layout.txt", ("대피로",)),
        ("b 구역 비상 탈출 경로 알려줘", "zone_B_layout.txt", ("대피로",)),
        ("C구역에서 불이 났는데 어디로 대피해?", "zone_C_layout.txt", ("대피로",)),
        ("사람이 숨을 안쉬는데 어떡해?", "edge_saver_manual.txt", ("심폐소생", "심정지")),
        ("호흡이 없어요", "edge_saver_manual.txt", ("심폐소생", "심정지")),
        ("의식이 없어요", "edge_saver_manual.txt", ("심폐소생", "심정지")),
    ]
    rows = []
    for query, source, evidence in cases:
        docs = manager.search(query)
        hit = any(doc.get("source") == source and any(word in doc.get("page_content", "") for word in evidence)
                  for doc in docs[:2])
        rows.append(dict(query=query, hit_at_2=hit, expected_source=source, documents=docs))
        print(f"{'PASS' if hit else 'FAIL'}: {query}")
    smoke_is_not_cpr = medical_intent("연기 때문에 숨쉬기 어려워요") != "cpr"
    missing_zone_status = None
    original = manager.metadata
    try:
        manager.metadata = [dict(doc, source="missing_layout.txt") if "zone_A_layout" in doc.get("source", "") else doc
                            for doc in original]
        empty = manager.search("A구역 대피로")
        missing_zone_status = not empty and manager.last_search_status == "missing_zone_document"
    finally:
        manager.metadata = original
    output = ROOT / "scratch/rag_quality_after.json"
    output.write_text(json.dumps(dict(results=rows, smoke_is_not_cpr=smoke_is_not_cpr,
                                     missing_zone_handled=missing_zone_status), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Relevant evidence at top 2: {sum(row['hit_at_2'] for row in rows)}/{len(rows)}; {output}")
    return 0 if all(row["hit_at_2"] for row in rows) and smoke_is_not_cpr and missing_zone_status else 1


if __name__ == "__main__":
    raise SystemExit(main())
