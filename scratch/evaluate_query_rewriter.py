import os
import sys
import time
import json

# 프로젝트 루트 확보
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import config
from rag.native_retriever import rag_manager
from rag.chain import rewrite_query_ollama

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

def run_rewriter_benchmark():
    print("=" * 70)
    print("[START] EdgeSaver 1.5B Query Rewriter Performance & Latency Benchmark")
    print("=" * 70)
    
    # RAG 모델 로드
    rag_manager.load_resources()
    
    # ── [실험 1] Baseline RAG (원본 쿼리 직접 검색 / Reranker가 복구된 상태인 경우 포함) ──
    print("\n[EVALUATOR] [Mode A] Baseline RAG (No Rewrite) 성능 측정 시작...")
    s1_hits = 0
    s1_mrr_sum = 0.0
    s1_latencies = []
    
    for item in EVALUATION_DATASET:
        query = item["query"]
        expected = item["expected_sources"]
        
        t0 = time.time()
        docs = rag_manager.search(query, top_k=4)
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
    
    print(f"-> Mode A 결과 | Hit Rate@1: {s1_hit_rate*100:.1f}% | MRR: {s1_mrr:.4f} | 평균지연: {s1_avg_lat:.3f}초")
    
    # ── [실험 2] 1.5B Query Rewriter RAG (Ollama 키워드 추출 보강 검색) ──
    print(f"\n[EVALUATOR] [Mode B] 1.5B Query Rewriter RAG (Model: {config.KEYWORD_MODEL}) 측정 시작...")
    s2_hits = 0
    s2_mrr_sum = 0.0
    s2_latencies = []
    ollama_latencies = []
    
    for idx, item in enumerate(EVALUATION_DATASET):
        query = item["query"]
        expected = item["expected_sources"]
        
        t0 = time.time()
        # 1. Ollama 1.5B를 통한 키워드 추출
        keywords = rewrite_query_ollama(query)
        t1 = time.time()
        
        # 2. 보강된 쿼리로 RAG 검색 수행
        search_query = f"{query} {keywords}" if keywords else query
        docs = rag_manager.search(search_query, top_k=4)
        t2 = time.time()
        
        tot_latency = t2 - t0
        ollama_lat = t1 - t0
        
        s2_latencies.append(tot_latency)
        ollama_latencies.append(ollama_lat)
        
        rank = 999
        for r_idx, doc in enumerate(docs):
            src = doc.get("source", "")
            if any(exp.lower() in src.lower() for exp in expected):
                rank = r_idx + 1
                break
                
        if rank == 1: s2_hits += 1
        if rank != 999: s2_mrr_sum += (1.0 / rank)
        
        print(f"[{idx+1:02d}] 원본: '{query[:15]}...' -> 키워드: '{keywords}' (추출: {ollama_lat:.2f}초 | 총합: {tot_latency:.2f}초)")
        
    s2_hit_rate = s2_hits / num_evals
    s2_mrr = s2_mrr_sum / num_evals
    s2_avg_lat = sum(s2_latencies) / num_evals
    s2_avg_ollama_lat = sum(ollama_latencies) / num_evals
    
    print(f"\n-> Mode B 결과 | Hit Rate@1: {s2_hit_rate*100:.1f}% | MRR: {s2_mrr:.4f} | 평균지연: {s2_avg_lat:.3f}초 (Ollama 대기: {s2_avg_ollama_lat:.3f}초)")
    
    # 3. 종합 비교 보고서 저장 및 출력
    report = {
        "baseline_no_rewrite": {
            "hit_rate_at_1": round(s1_hit_rate, 4),
            "mrr": round(s1_mrr, 4),
            "avg_latency_sec": round(s1_avg_lat, 4)
        },
        "rewriter_1_5b_active": {
            "hit_rate_at_1": round(s2_hit_rate, 4),
            "mrr": round(s2_mrr, 4),
            "avg_latency_sec": round(s2_avg_lat, 4),
            "avg_ollama_inference_sec": round(s2_avg_ollama_lat, 4)
        }
    }
    
    print("\n" + "=" * 80)
    print("[FINAL REPORT] 1.5B 쿼리 재작성 전후 성능/지연 정량 비교 분석표")
    print("=" * 80)
    print(f"{'구동 모드':<32} | {'Hit Rate @ 1':<14} | {'MRR':<10} | {'평균 지연 속도 (sec)':<20}")
    print("-" * 80)
    print(f"{'Baseline RAG (No Rewrite)':<32} | {s1_hit_rate*100:.1f}%{'':<9} | {s1_mrr:.4f}{'':<6} | {s1_avg_lat:.3f}초")
    print(f"{'1.5B Query Rewriter RAG':<32} | {s2_hit_rate*100:.1f}%{'':<9} | {s2_mrr:.4f}{'':<6} | {s2_avg_lat:.3f}초 (Ollama: {s2_avg_ollama_lat:.2f}초)")
    print("=" * 80)
    
    report_path = os.path.join(PROJECT_ROOT, "data", "query_rewriter_comparison_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=4)
    print(f"[FILE] 1.5B 시간지연 분석 JSON 리포트가 성공적으로 저장되었습니다: {report_path}")

if __name__ == "__main__":
    run_rewriter_benchmark()
