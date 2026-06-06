import os
import sys
import time
import json

# 프로젝트 루트 확보
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import config
from sentence_transformers import SentenceTransformer
from sentence_transformers.cross_encoder import CrossEncoder
from rag.native_retriever import rag_manager

# Windows CMD 한글 인코딩 강제 매핑 및 이모지 깨짐 방지
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# 1. 벤치마크용 비상 시나리오 질문 세트 (15개 항목)
EVALUATION_DATASET = [
    {"query": "A구역 화재시 대피방법은?", "expected_sources": ["zone_A_layout.txt"], "category": "zone_evacuation"},
    {"query": "B구역 비상 탈출 경로 알려줘", "expected_sources": ["zone_B_layout.txt"], "category": "zone_evacuation"},
    {"query": "C구역에서 불이 났는데 어디로 대피해?", "expected_sources": ["zone_C_layout.txt"], "category": "zone_evacuation"},
    {"query": "사람이 숨을 안쉬는데 어떡해?", "expected_sources": ["edge_saver_manual.txt", "[자료] 119생활응급처치매뉴얼 및 핸드북.hwp"], "category": "emergency_cpr"},
    {"query": "높은데서 떨어져서 뼈가 부러진거 같아 어떻게 해?", "expected_sources": ["edge_saver_manual.txt", "[자료] 119생활응급처치매뉴얼 및 핸드북.hwp"], "category": "emergency_injury"},
    {"query": "피가 멈추지 않고 철철 흘러 지혈 어떻게 하지?", "expected_sources": ["edge_saver_manual.txt", "[자료] 119생활응급처치매뉴얼 및 핸드북.hwp"], "category": "emergency_injury"},
    {"query": "아파트 불났는데 문밖으로 연기가 들어오면 어떡함?", "expected_sources": ["(아파트 입주자) 화재 피난행동요령.pdf"], "category": "apartment_fire"},
    {"query": "아파트에서 이웃집에 불이 났을 때 대기해야 하나 대피해야 하나?", "expected_sources": ["(아파트 입주자) 화재 피난행동요령.pdf"], "category": "apartment_fire"},
    {"query": "아파트 엘리베이터 타고 대피해도 됨?", "expected_sources": ["(아파트 입주자) 화재 피난행동요령.pdf"], "category": "apartment_fire"},
    {"query": "공장에서 화학물질이 누출됐는데 어떡하지?", "expected_sources": ["edge_saver_manual.txt", "factory_gas_manual.txt"], "category": "factory_accident"},
    {"query": "기계 벨트에 팔이 끼었어 비상 정지 어떻게 해?", "expected_sources": ["edge_saver_manual.txt", "factory_fire_manual.txt"], "category": "factory_accident"},
    {"query": "배전반에서 불꽃이 튀면서 전기 화재 났어 물 뿌려도 됨?", "expected_sources": ["factory_fire_manual.txt", "소화기구에관한설명_수동식소화기(설치장소, 분류).hwp"], "category": "factory_accident"},
    {"query": "유독가스가 유출됐을 때 대피 요령은?", "expected_sources": ["edge_saver_manual.txt", "factory_gas_manual.txt"], "category": "factory_accident"},
    {"query": "산에서 길을 잃고 조난당했을 때 수칙", "expected_sources": ["edge_saver_manual.txt"], "category": "mountain_accident"},
    {"query": "산사태나 낙석이 발생했을 때 대처 방법", "expected_sources": ["edge_saver_manual.txt"], "category": "mountain_accident"}
]

# 2. 비교 대상 Reranker 모델 목록
BENCHMARK_MODELS = {
    "MiniLM (초경량/영어위주)": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "bge-m3-ko (중간체급/한국어특화)": "dragonkue/bge-reranker-v2-m3-ko",
    "BGE-Base (중중량급/의미론우수)": "BAAI/bge-reranker-base"
}

def evaluate_model(model_name: str, model_path: str):
    """지정된 모델의 QA 셋 성능 및 속도를 일괄 측정합니다."""
    print(f"\n[EVALUATOR] 로드 중: {model_name} ({model_path})...")
    
    try:
        # CPU 엣지 최적화 추론 강제
        reranker = CrossEncoder(model_path, device="cpu")
        print(f"[SUCCESS] {model_name} 로딩 완료.")
    except Exception as e:
        print(f"[ERROR] {model_name} 로드 실패: {e}")
        return None
        
    hits_at_1 = 0
    mrr_sum = 0.0
    latencies = []
    
    for item in EVALUATION_DATASET:
        query = item["query"]
        expected = item["expected_sources"]
        
        # 1단계 검색 수집 (후보 10개)
        t0 = time.time()
        stage1_docs = rag_manager.search(query, top_k=10)
        
        # 2단계 Reranker 정렬
        if stage1_docs:
            pairs = [[query, doc.get("page_content", "")] for doc in stage1_docs]
            scores = reranker.predict(pairs)
            scored = list(zip(scores, stage1_docs))
            scored.sort(key=lambda x: x[0], reverse=True)
            stage2_docs = [doc for _, doc in scored]
        else:
            stage2_docs = []
        t1 = time.time()
        
        latency = t1 - t0
        latencies.append(latency)
        
        # 지표 연산
        rank = 999
        for r_idx, doc in enumerate(stage2_docs):
            src = doc.get("source", "")
            if any(exp.lower() in src.lower() for exp in expected):
                rank = r_idx + 1
                break
                
        if rank == 1:
            hits_at_1 += 1
        if rank != 999:
            mrr_sum += (1.0 / rank)
            
    num_evals = len(EVALUATION_DATASET)
    avg_latency = sum(latencies) / num_evals
    hit_rate = hits_at_1 / num_evals
    mrr = mrr_sum / num_evals
    
    print(f"-> 결과 [ {model_name} ] | Hit Rate@1: {hit_rate*100:.1f}% | MRR: {mrr:.4f} | 평균지연: {avg_latency:.3f}초")
    
    # 메모리 해제 보조
    del reranker
    import gc
    gc.collect()
    
    return {
        "hit_rate_at_1": round(hit_rate, 4),
        "mrr": round(mrr, 4),
        "avg_latency_sec": round(avg_latency, 4)
    }

def run_multi_benchmark():
    print("=" * 65)
    print("[START] EdgeSaver Multi-Model Reranker Unified Benchmarking")
    print("=" * 65)
    
    rag_manager.load_resources()
    
    # 1. 1단계 Baseline 결과 측정
    print("\n[EVALUATOR] 1단계 Baseline RAG 성능 측정 시작...")
    s1_hits = 0
    s1_mrr_sum = 0.0
    s1_latencies = []
    
    for item in EVALUATION_DATASET:
        query = item["query"]
        expected = item["expected_sources"]
        
        t0 = time.time()
        docs = rag_manager.search(query, top_k=4) # 실제 가동 컷오프(4) 기준 측정
        t1 = time.time()
        
        s1_latencies.append(t1 - t0)
        
        rank = 999
        for r_idx, doc in enumerate(docs):
            src = doc.get("source", "")
            if any(exp.lower() in src.lower() for exp in expected):
                rank = r_idx + 1
                break
                
        if rank == 1: s1_hits += 1
        if rank != 999: s1_mrr_sum += (1.0 / rank)
        
    num_evals = len(EVALUATION_DATASET)
    s1_hit_rate = s1_hits / num_evals
    s1_mrr = s1_mrr_sum / num_evals
    s1_avg_lat = sum(s1_latencies) / num_evals
    
    print(f"-> 결과 [ Baseline RAG (Top-4) ] | Hit Rate@1: {s1_hit_rate*100:.1f}% | MRR: {s1_mrr:.4f} | 평균지연: {s1_avg_lat:.3f}초")
    
    report = {
        "baseline_rag": {
            "hit_rate_at_1": round(s1_hit_rate, 4),
            "mrr": round(s1_mrr, 4),
            "avg_latency_sec": round(s1_avg_lat, 4)
        },
        "reranker_models": {}
    }
    
    # 2. 각 Reranker 모델별 성능 측정
    for name, path in BENCHMARK_MODELS.items():
        res = evaluate_model(name, path)
        if res:
            report["reranker_models"][name] = res
            
    # 3. 종합 요약 비교 테이블 출력
    print("\n" + "=" * 80)
    print("[FINAL REPORT] Reranker 멀티모델 성능 통합 대조표")
    print("=" * 80)
    print(f"{'모델명 (체급)':<32} | {'Hit Rate @ 1':<14} | {'MRR':<10} | {'평균 CPU 속도 (sec)':<20}")
    print("-" * 80)
    print(f"{'Baseline RAG (No Rerank)':<32} | {s1_hit_rate*100:.1f}%{'':<9} | {s1_mrr:.4f}{'<':<6} | {s1_avg_lat:.3f}초")
    print("-" * 80)
    
    for name, metrics in report["reranker_models"].items():
        print(f"{name:<32} | {metrics['hit_rate_at_1']*100:.1f}%{'':<9} | {metrics['mrr']:.4f}{'':<6} | {metrics['avg_latency_sec']:.3f}초")
    print("=" * 80)
    
    # JSON 파일 출력
    report_path = os.path.join(PROJECT_ROOT, "data", "multi_reranker_comparison_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=4)
    print(f"[FILE] 비교 분석 상세 JSON 리포트가 저장되었습니다: {report_path}")

if __name__ == "__main__":
    run_multi_benchmark()
