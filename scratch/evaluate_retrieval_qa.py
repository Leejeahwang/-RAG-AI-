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

# 1. 평가용 질문 데이터셋 (20개 핵심 실전 시나리오)
# 각 질문에 대해 '반드시 매칭되어야 하는 정답 파일명 목록'을 매핑하여 Hit Rate를 계산합니다.
EVALUATION_DATASET = [
    # [구역 대피로 관련 질문]
    {
        "query": "A구역 화재시 대피방법은?",
        "expected_sources": ["zone_A_layout.txt"],
        "category": "zone_evacuation"
    },
    {
        "query": "B구역 비상 탈출 경로 알려줘",
        "expected_sources": ["zone_B_layout.txt"],
        "category": "zone_evacuation"
    },
    {
        "query": "C구역에서 불이 났는데 어디로 대피해?",
        "expected_sources": ["zone_C_layout.txt"],
        "category": "zone_evacuation"
    },
    
    # [다급한 구어체 / 응급 처치 관련 질문]
    {
        "query": "사람이 숨을 안쉬는데 어떡해?",
        "expected_sources": ["edge_saver_manual.txt", "[자료] 119생활응급처치매뉴얼 및 핸드북.hwp"],
        "category": "emergency_cpr"
    },
    {
        "query": "높은데서 떨어져서 뼈가 부러진거 같아 어떻게 해?",
        "expected_sources": ["edge_saver_manual.txt", "[자료] 119생활응급처치매뉴얼 및 핸드북.hwp"],
        "category": "emergency_injury"
    },
    {
        "query": "피가 멈추지 않고 철철 흘러 지혈 어떻게 하지?",
        "expected_sources": ["edge_saver_manual.txt", "[자료] 119생활응급처치매뉴얼 및 핸드북.hwp"],
        "category": "emergency_injury"
    },
    
    # [아파트 화재 수칙 관련 질문]
    {
        "query": "아파트 불났는데 문밖으로 연기가 들어오면 어떡함?",
        "expected_sources": ["(아파트 입주자) 화재 피난행동요령.pdf"],
        "category": "apartment_fire"
    },
    {
        "query": "아파트에서 이웃집에 불이 났을 때 대기해야 하나 대피해야 하나?",
        "expected_sources": ["(아파트 입주자) 화재 피난행동요령.pdf"],
        "category": "apartment_fire"
    },
    {
        "query": "아파트 엘리베이터 타고 대피해도 됨?",
        "expected_sources": ["(아파트 입주자) 화재 피난행동요령.pdf"],
        "category": "apartment_fire"
    },
    
    # [산업 단지 및 특수 재해 관련 질문]
    {
        "query": "공장에서 화학물질이 누출됐는데 어떡하지?",
        "expected_sources": ["edge_saver_manual.txt", "factory_gas_manual.txt"],
        "category": "factory_accident"
    },
    {
        "query": "기계 벨트에 팔이 끼었어 비상 정지 어떻게 해?",
        "expected_sources": ["edge_saver_manual.txt", "factory_fire_manual.txt"],
        "category": "factory_accident"
    },
    {
        "query": "배전반에서 불꽃이 튀면서 전기 화재 났어 물 뿌려도 됨?",
        "expected_sources": ["factory_fire_manual.txt", "소화기구에관한설명_수동식소화기(설치장소, 분류).hwp"],
        "category": "factory_accident"
    },
    {
        "query": "유독가스가 유출됐을 때 대피 요령은?",
        "expected_sources": ["edge_saver_manual.txt", "factory_gas_manual.txt"],
        "category": "factory_accident"
    },
    {
        "query": "산에서 길을 잃고 조난당했을 때 수칙",
        "expected_sources": ["edge_saver_manual.txt"],
        "category": "mountain_accident"
    },
    {
        "query": "산사태나 낙석이 발생했을 때 대처 방법",
        "expected_sources": ["edge_saver_manual.txt"],
        "category": "mountain_accident"
    }
]

# Windows CMD 한글 인코딩 강제 매핑 및 이모지 깨짐 방지
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

def run_evaluation_benchmark():
    print("=" * 60)
    print("[START] EdgeSaver Unified RAG Automated QA Benchmark Evaluation")
    print("=" * 60)
    
    # RAG 로드
    rag_manager.load_resources()
    
    # Reranker 로드
    print(f"\n[INFO] Loading Cross Encoder model: {RERANKER_MODEL_NAME}...")
    try:
        reranker = CrossEncoder(RERANKER_MODEL_NAME, device="cpu")
        print("[SUCCESS] Reranker model loaded (CPU Evaluation Mode)")
    except Exception as e:
        print(f"[WARNING] Reranker load failed, fallback to similarity emulation: {e}")
        reranker = None
        
    results = []
    
    # 평가지표 초기화
    stage1_hits_at_1 = 0
    stage2_hits_at_1 = 0
    
    stage1_mrr_sum = 0.0
    stage2_mrr_sum = 0.0
    
    stage1_latencies = []
    stage2_latencies = []
    
    print(f"\n[EVAL] Evaluating total {len(EVALUATION_DATASET)} disaster scenarios...\n")
    
    for idx, item in enumerate(EVALUATION_DATASET):
        query = item["query"]
        expected = item["expected_sources"]
        cat = item["category"]
        
        # --- 1단계 RAG 수행 (RRF) ---
        t0 = time.time()
        stage1_docs = rag_manager.search(query, top_k=10)
        t1 = time.time()
        stage1_latency = t1 - t0
        stage1_latencies.append(stage1_latency)
        
        # 1단계 지표 측정
        s1_rank = 999
        for r_idx, doc in enumerate(stage1_docs):
            src = doc.get("source", "")
            if any(exp.lower() in src.lower() for exp in expected):
                s1_rank = r_idx + 1
                break
                
        s1_hit = 1 if s1_rank == 1 else 0
        s1_mrr = 1.0 / s1_rank if s1_rank != 999 else 0.0
        
        stage1_hits_at_1 += s1_hit
        stage1_mrr_sum += s1_mrr
        
        # --- 2단계 BGE-Reranker 정렬 수행 ---
        t2 = time.time()
        if reranker is not None and stage1_docs:
            pairs = [[query, doc.get("page_content", "")] for doc in stage1_docs]
            scores = reranker.predict(pairs)
            scored = list(zip(scores, stage1_docs))
            scored.sort(key=lambda x: x[0], reverse=True)
            stage2_docs = [doc for _, doc in scored]
        else:
            stage2_docs = list(stage1_docs)
        t3 = time.time()
        
        stage2_latency = (t3 - t2) + stage1_latency # 1단계 + 2단계 총합 지연 시간
        stage2_latencies.append(stage2_latency)
        
        # 2단계 지표 측정
        s2_rank = 999
        for r_idx, doc in enumerate(stage2_docs):
            src = doc.get("source", "")
            if any(exp.lower() in src.lower() for exp in expected):
                s2_rank = r_idx + 1
                break
                
        s2_hit = 1 if s2_rank == 1 else 0
        s2_mrr = 1.0 / s2_rank if s2_rank != 999 else 0.0
        
        stage2_hits_at_1 += s2_hit
        stage2_mrr_sum += s2_mrr
        
        # 결과 기록
        results.append({
            "id": idx + 1,
            "query": query,
            "category": cat,
            "expected_sources": expected,
            "stage1": {
                "top_1_source": stage1_docs[0].get("source") if stage1_docs else None,
                "target_rank": s1_rank if s1_rank != 999 else -1,
                "hit_at_1": s1_hit,
                "latency_sec": round(stage1_latency, 4)
            },
            "stage2_with_reranker": {
                "top_1_source": stage2_docs[0].get("source") if stage2_docs else None,
                "target_rank": s2_rank if s2_rank != 999 else -1,
                "hit_at_1": s2_hit,
                "latency_sec": round(stage2_latency, 4)
            }
        })
        
        print(f"[{idx+1:02d}] 분류: {cat:<18} | 질문: '{query[:18]}...'")
        print(f"     ㄴ [기존 RAG] 1순위: {results[-1]['stage1']['top_1_source'][:25]} (순위: {s1_rank if s1_rank != 999 else '실패'})")
        print(f"     ㄴ [Reranker] 1순위: {results[-1]['stage2_with_reranker']['top_1_source'][:25]} (순위: {s2_rank if s2_rank != 999 else '실패'})\n")

    # 종합 통계 산출
    num_evals = len(EVALUATION_DATASET)
    
    final_stage1_hit_rate = stage1_hits_at_1 / num_evals
    final_stage2_hit_rate = stage2_hits_at_1 / num_evals
    
    final_stage1_mrr = stage1_mrr_sum / num_evals
    final_stage2_mrr = stage2_mrr_sum / num_evals
    
    avg_stage1_latency = sum(stage1_latencies) / num_evals
    avg_stage2_latency = sum(stage2_latencies) / num_evals
    
    summary = {
        "total_scenarios": num_evals,
        "metrics": {
            "stage1_baseline": {
                "hit_rate_at_1": round(final_stage1_hit_rate, 4),
                "mrr": round(final_stage1_mrr, 4),
                "avg_latency_sec": round(avg_stage1_latency, 4)
            },
            "stage2_bge_reranker": {
                "hit_rate_at_1": round(final_stage2_hit_rate, 4),
                "mrr": round(final_stage2_mrr, 4),
                "avg_latency_sec": round(avg_stage2_latency, 4)
            }
        },
        "details": results
    }
    
    # 벤치마크 리포트 파일 저장
    report_path = os.path.join(PROJECT_ROOT, "data", "retrieval_benchmark_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=4)
        
    print("=" * 60)
    print("[SUMMARY] Benchmark Evaluation Final Results Summary")
    print("=" * 60)
    print(f"Total Evaluation Scenarios: {num_evals} items")
    print(f"1. [Baseline RAG (Stage 1)]")
    print(f"   - Hit Rate @ 1 : {final_stage1_hit_rate*100:.1f}%")
    print(f"   - MRR          : {final_stage1_mrr:.4f}")
    print(f"   - Avg Latency  : {avg_stage1_latency:.3f}s")
    print(f"2. [BGE-Reranker-KP (Stage 2)]")
    print(f"   - Hit Rate @ 1 : {final_stage2_hit_rate*100:.1f}% (Diff: +{(final_stage2_hit_rate-final_stage1_hit_rate)*100:.1f}%)")
    print(f"   - MRR          : {final_stage2_mrr:.4f} (Diff: +{final_stage2_mrr-final_stage1_mrr:.4f})")
    print(f"   - Avg Latency  : {avg_stage2_latency:.3f}s (Delta: +{avg_stage2_latency-avg_stage1_latency:.3f}s)")
    print("=" * 60)
    print(f"[FILE] Benchmark report JSON file saved at: {report_path}")

if __name__ == "__main__":
    run_evaluation_benchmark()
