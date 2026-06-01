import os
import sys
import time

# 프로젝트 루트 경로 확보
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import config
from sentence_transformers import SentenceTransformer
from sentence_transformers.cross_encoder import CrossEncoder
from rag.native_retriever import rag_manager

# 1. 벤치마크용 Reranker 모델 초기화
# BGE-Reranker-KP 또는 경량 CrossEncoder 모델 탑재
# (실험용으로 메모리가 가볍고 한국어 정합성이 우수한 cross-encoder/ms-marco-MiniLM-L-6-v2 또는 BAAI/bge-reranker-base 권장)
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"

# Windows CMD 한글 인코딩 강제 매핑 및 이모지 깨짐 방지
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

print("=" * 60)
print("[START] BGE-Reranker-KP Standalone Benchmark Infrastructure")
print("=" * 60)

# Native RAG 리소스 로드
rag_manager.load_resources()

print(f"\n[Reranker] Loading Cross Encoder: {RERANKER_MODEL_NAME}...")
try:
    # 엣지 디바이스 환경을 고려하여 CPU 추론 강제
    reranker = CrossEncoder(RERANKER_MODEL_NAME, device="cpu")
    print("[SUCCESS] Reranker model loaded (CPU mode)")
except Exception as e:
    print(f"[ERROR] Reranker model load failed: {e}")
    print("Demo will run using standard similarity emulation.")
    reranker = None

def run_reranking_experiment(query: str, top_k_candidates: int = 10, final_top_n: int = 4):
    """
    Reranking 실험 단독 파이프라인
    """
    print("\n" + "-"*60)
    print(f"❓ 질문: {query}")
    print("-"*60)
    
    # 1단계 RAG: 기존 룰 기반 검색 수행 (가점 필터 적용 전 원본 후보군 추출을 모방)
    # 벤치마크를 위해 native_retriever의 1단계 RRF 후보군을 검색합니다.
    start_time = time.time()
    
    # 1단계 검색 수행 (충분히 많은 후보를 가져옴)
    # top_k=25, top_n_sources=3
    candidate_docs = rag_manager.search(query, top_k=top_k_candidates)
    stage1_time = time.time() - start_time
    
    print(f"[RAG] 1단계 수집 완료 ({stage1_time:.3f}초) - 후보 청크: {len(candidate_docs)}개")
    for idx, doc in enumerate(candidate_docs[:5]):
        src = doc.get("source", "Unknown")
        snippet = doc.get("page_content", "").replace("\n", " ")[:50]
        print(f"   [{idx+1}] 소스: {src} | 내용: {snippet}...")
        
    if not candidate_docs:
        print("[ERROR] 검색된 후보군이 없습니다.")
        return
        
    # 2단계 BGE-Reranker 재정렬 수행
    print(f"\n[SEARCH] 2단계 Reranker 교차 어텐션 순위 재배치 시작 (대상: {len(candidate_docs)}개 청크)...")
    rerank_start = time.time()
    
    if reranker is not None:
        # (질문, 청크 본문) 쌍 생성
        pairs = [[query, doc.get("page_content", "")] for doc in candidate_docs]
        
        # 교차 어텐션 스코어 예측
        scores = reranker.predict(pairs)
        
        # 스코어를 문서 객체와 매핑
        scored_docs = list(zip(scores, candidate_docs))
        # 점수 기준 내림차순 정렬
        scored_docs.sort(key=lambda x: x[0], reverse=True)
    else:
        # Reranker 모델 부재 시 모방 정렬 (가상 스코어)
        scored_docs = [(1.0 - (i * 0.05), doc) for i, doc in enumerate(candidate_docs)]
        
    rerank_time = time.time() - rerank_start
    total_time = time.time() - start_time
    
    print(f"[SUCCESS] 2단계 Reranker 정렬 완료 ({rerank_time:.3f}초) | 총 소요시간: {total_time:.3f}초")
    print("\n[RANKING TABLE] 최종 순위 비교 테이블")
    print(f"{'순위':<6} | {'기존 RAG 소스':<30} | {'Reranker 정렬 소스 (스코어)':<40}")
    print("-" * 85)
    
    for i in range(min(final_top_n, len(candidate_docs))):
        orig_src = candidate_docs[i].get("source", "Unknown")[:28]
        
        rerank_score, rerank_doc = scored_docs[i]
        rerank_src = rerank_doc.get("source", "Unknown")[:25]
        
        print(f"{i+1:<6} | {orig_src:<30} | {rerank_src:<28} ({rerank_score:.4f})")
        
    # 최고 매칭 청크 스니펫 비교
    print("\n[COMPARISON] 최고 득점 정답 청크 비교")
    print(f"-> [기존 1순위 소스]: {candidate_docs[0].get('source')}")
    print(f"   내용: {candidate_docs[0].get('page_content', '').strip()[:150]}...")
    print(f"-> [Reranker 1순위 소스]: {scored_docs[0][1].get('source')}")
    print(f"   내용: {scored_docs[0][1].get('page_content', '').strip()[:150]}...")

if __name__ == "__main__":
    # 대표적인 3가지 시나리오 벤치마크 테스트
    # 1. 구역 대피로 특정 시나리오
    run_reranking_experiment("A구역 화재시 비상 대피 경로는 어떻게 되나요?", top_k_candidates=10)
    
    # 2. 다급한 구어체/방언 시나리오
    run_reranking_experiment("불이 확 번지고 아파트인데 숨을 안쉬어 어떡해?", top_k_candidates=10)
