"""
Native RAG 엔진 (v30)
Ollama/Chroma 의존성 없이 FAISS와 Sentence-Transformers를 직접 사용하여 
호환성과 속도를 극대화한 검색 모듈입니다.
"""

import os
import re
import math
import numpy as np
import faiss
import pickle
from sentence_transformers import SentenceTransformer
try:
    from sentence_transformers.cross_encoder import CrossEncoder
except ImportError:
    CrossEncoder = None
from typing import List, Dict, Any
import config
from collections import Counter

class SimpleBM25:
    """
    Pure Python lightweight BM25 engine.
    Includes character-level bigram expansion to support spacing-robust Korean matching.
    """
    def __init__(self, corpus: List[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_lengths = []
        self.doc_freqs = []
        self.nd = {} # term -> doc count
        self.idf = {}
        self.avg_doc_length = 0.0
        
        tokenized_corpus = [self.tokenize(doc) for doc in corpus]
        self.doc_lengths = [len(doc) for doc in tokenized_corpus]
        self.avg_doc_length = sum(self.doc_lengths) / self.corpus_size if self.corpus_size > 0 else 1.0
        
        for doc in tokenized_corpus:
            frequencies = {}
            for term in doc:
                frequencies[term] = frequencies.get(term, 0) + 1
            self.doc_freqs.append(frequencies)
            for term in frequencies.keys():
                self.nd[term] = self.nd.get(term, 0) + 1
                
        for term, freq in self.nd.items():
            self.idf[term] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

    def tokenize(self, text: str) -> List[str]:
        # 영어, 숫자 및 한국어 음절을 추출
        words = re.findall(r'[a-zA-Z0-9가-힣]+', text.lower())
        tokens = list(words)
        # 한국어 조사 분리 취약점을 보정하기 위한 음절 Bigram 추가
        for w in words:
            if len(w) > 1:
                for i in range(len(w) - 1):
                    tokens.append(w[i:i+2])
        return tokens

    def get_scores(self, query: str) -> List[float]:
        query_tokens = self.tokenize(query)
        scores = []
        for i in range(self.corpus_size):
            score = 0.0
            doc_len = self.doc_lengths[i]
            freqs = self.doc_freqs[i]
            for term in query_tokens:
                if term in freqs:
                    tf = freqs[term]
                    idf = self.idf.get(term, 0.0)
                    numerator = idf * tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_length)
                    score += numerator / denominator
            scores.append(score)
        return scores

class NativeRAGManager:
    def __init__(self):
        self.model = None
        self.index = None
        self.bm25 = None
        self.metadata = []
        self.reranker = None
        self.model_name = config.NATIVE_EMBEDDING_MODEL
        self.index_dir = config.FAISS_INDEX_DIR
        self.index_file = os.path.join(self.index_dir, "index.faiss")
        self.meta_file = os.path.join(self.index_dir, "metadata.pkl")
        self.bm25_file = os.path.join(self.index_dir, "bm25.pkl")

    def load_resources(self):
        """임베딩 모델 및 FAISS 인덱스, BM25 모델 로드"""
        print(f"[NativeRAG] 모델 로드 중: {self.model_name}...")
        self.model = SentenceTransformer(self.model_name)
        
        if os.path.exists(self.index_file) and os.path.exists(self.meta_file):
            print(f"[NativeRAG] 기존 인덱스 로드 중: {self.index_file}")
            self.index = faiss.read_index(self.index_file)
            with open(self.meta_file, 'rb') as f:
                self.metadata = pickle.load(f)
            
            if os.path.exists(self.bm25_file):
                print(f"[NativeRAG] 기존 BM25 로드 중: {self.bm25_file}")
                with open(self.bm25_file, 'rb') as f:
                    self.bm25 = pickle.load(f)
            
            print(f"[NativeRAG] 로드 완료 (데이터: {len(self.metadata)}개)")
            
            # Reranker 모델 CPU 사전 로드 기작
            if getattr(config, "USE_RERANKER", False) and CrossEncoder is not None:
                reranker_model = getattr(config, "RERANKER_MODEL_NAME", "BAAI/bge-reranker-base")
                print(f"[NativeRAG] Reranker 로드 중: {reranker_model}...")
                try:
                    self.reranker = CrossEncoder(reranker_model, device="cpu")
                    print(f"[NativeRAG] Reranker 로드 완료: {reranker_model}")
                except Exception as e:
                    print(f"[NativeRAG] Reranker 로드 실패 (Lexical Fallback 준비): {e}")
                    self.reranker = None
        else:
            print("[NativeRAG] 기존 인덱스가 없습니다. 초기 구축이 필요합니다.")

    def build_index(self, chunks: List[Any]):
        """새로운 청크(Document 객체 또는 Dict)를 기반으로 인덱스 구축"""
        if not chunks:
            print("[NativeRAG] 구축할 데이터가 없습니다.")
            return

        print(f"[NativeRAG] 인덱스 구축 시작 (대상: {len(chunks)}개)...")
        # Document 객체 호환성 처리
        self.metadata = []
        texts = []
        for c in chunks:
            if hasattr(c, 'page_content'): # LangChain Document
                texts.append(c.page_content)
                meta = c.metadata.copy()
                meta['page_content'] = c.page_content # 내부 검색 결과 활용을 위해 원문 포함
                self.metadata.append(meta)
            else: # Dict
                texts.append(c.get('page_content', ''))
                self.metadata.append(c)

        embeddings = self.model.encode(texts, show_progress_bar=True)
        
        # FAISS 인덱스 생성 (L2 거리 기준)
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings.astype('float32'))
        
        # BM25 생성
        self.bm25 = SimpleBM25(texts)
        
        # 파일 저장
        if not os.path.exists(self.index_dir):
            os.makedirs(self.index_dir)
        faiss.write_index(self.index, self.index_file)
        with open(self.meta_file, 'wb') as f:
            pickle.dump(self.metadata, f)
        with open(self.bm25_file, 'wb') as f:
            pickle.dump(self.bm25, f)
        
        print(f"[NativeRAG] 인덱스 구축 및 저장 완료: {self.index_file}, {self.bm25_file}")

    def search(self, query: str, top_k: int = 25, top_n_sources: int = 3) -> List[Dict[str, Any]]:
        """지능형 필터링 및 RRF 하이브리드 검색, 그리고 2차 리랭킹"""
        if self.index is None:
            print("[NativeRAG] 에러: 인덱스가 로드되지 않았습니다.")
            return []

        # 1. FAISS 검색 수행
        query_vec = self.model.encode([query]).astype('float32')
        distances, indices = self.index.search(query_vec, top_k)
        
        faiss_ranks = {}
        for rank_idx, doc_idx in enumerate(indices[0]):
            if doc_idx != -1:
                faiss_ranks[doc_idx] = rank_idx + 1

        # 2. BM25 검색 수행
        bm25_ranks = {}
        if self.bm25 is not None:
            bm25_scores = self.bm25.get_scores(query)
            scored_docs = [(score, doc_idx) for doc_idx, score in enumerate(bm25_scores) if score > 0]
            scored_docs.sort(key=lambda x: x[0], reverse=True)
            for rank_idx, (_, doc_idx) in enumerate(scored_docs[:top_k]):
                bm25_ranks[doc_idx] = rank_idx + 1

        # 3. RRF (Reciprocal Rank Fusion) 통합
        rrf_scores = {}
        all_candidate_indices = set(list(faiss_ranks.keys()) + list(bm25_ranks.keys()))
        
        RRF_K = 60
        for doc_idx in all_candidate_indices:
            f_rank = faiss_ranks.get(doc_idx, 99999)
            b_rank = bm25_ranks.get(doc_idx, 99999)
            
            rrf_score = (1.0 / (RRF_K + f_rank)) + (1.0 / (RRF_K + b_rank))
            rrf_scores[doc_idx] = rrf_score
            
        sorted_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        selected_candidates = [doc_idx for doc_idx, _ in sorted_candidates[:top_k]]

        # 4. 주제/장소 하드 필터링 (v28 logic porting)
        CONFLICT_MAP = {
            "화재": ["화재", "불", "소화", "피난", "방화", "소방", "소화기"],
            "화산": ["화산", "낙진", "재", "용암"],
            "태풍": ["태풍", "강풍", "홍수", "침수", "해일"],
            "폭발": ["폭발", "가스", "유출", "화학"]
        }
        LOCATION_MAP = {
            "아파트": ["아파트", "공동주택", "입주자", "세대", "주거", "단지내", "관리사무소"],
            "공장": ["공장", "산업", "작업장", "배전반", "창고", "기계", "설비", "factory", "제조"],
            "산악": ["산악", "국립공원", "등산", "조난", "등산로", "계곡"]
        }
        
        detected_themes = [theme for theme, keywords in CONFLICT_MAP.items() if any(k in query for k in keywords)]
        detected_locs = [loc for loc, keywords in LOCATION_MAP.items() if any(k in query.lower() for k in keywords)]
        
        valid_results = []
        for idx in selected_candidates:
            doc = self.metadata[idx]
            src = doc.get('source', 'unknown').lower()
            content = doc.get('page_content', '')[:200].lower()
            
            # 필터링 판별
            doc_theme = next((theme for theme, keywords in CONFLICT_MAP.items() if any(k in src for k in keywords) or any(k in content for k in keywords)), None)
            doc_loc = next((loc for loc, keywords in LOCATION_MAP.items() if any(k in src for k in keywords) or any(k in content for k in keywords)), None)
            
            # 구역 평면도/대피로(zone, layout) 파일은 공장 핵심 지표이므로 필터링에서 예외 처리 또는 공장으로 분류
            if "zone" in src or "layout" in src:
                doc_loc = "공장"
            
            if detected_themes and doc_theme and doc_theme not in detected_themes: continue
            if detected_locs and doc_loc and doc_loc not in detected_locs: continue
            
            # [Strict 구역 필터링] 
            # 질문에서 특정 구역이 감지되었는데, 이 문서가 다른 구역의 레이아웃인 경우 RAG 후보에서 완전히 제외시킵니다.
            target_zones_in_query = []
            for zc in ["A", "B", "C"]:
                if f"{zc}구역" in query or f"{zc} 구역" in query or f"zone_{zc.lower()}" in query or f"zone_{zc.upper()}" in query:
                    target_zones_in_query.append(zc)
            
            # 질문에 특정 구역이 명시되어 있는데, 다른 구역의 레이아웃 파일인 경우 즉시 버림
            is_unrelated_zone = False
            if target_zones_in_query:
                for zc in ["A", "B", "C"]:
                    if zc not in target_zones_in_query:
                        if f"zone_{zc.lower()}" in src or f"zone_{zc.upper()}" in src:
                            is_unrelated_zone = True
                            break
            if is_unrelated_zone:
                continue

            valid_results.append(doc)

        if not valid_results:
            return [self.metadata[i] for i in selected_candidates[:1]] if selected_candidates else []

        # 5. 단일 소스 집중 (v24 logic)
        source_scores = Counter()
        for i, doc in enumerate(valid_results[:10]):
            src = doc.get('source', 'unknown')
            source_scores[src] += (10 - i)
            
        winner_sources = [s for s, score in source_scores.most_common(top_n_sources)]
        # [품질 보강] 질문에 매칭되는 정확한 구역 정보 소스만 winner_sources 필터를 우회하여 강제 보존합니다.
        final_docs = []
        for d in valid_results:
            src = d.get('source', '')
            
            # 현재 질문에 감지된 대상 구역
            target_zones_in_query = [zc for zc in ["A", "B", "C"] if f"{zc}구역" in query or f"{zc} 구역" in query or f"zone_{zc.lower()}" in query or f"zone_{zc.upper()}" in query]
            
            is_matched_critical_zone = False
            if target_zones_in_query:
                # 질문에 해당하는 특정 구역 파일만 예외 보존 처리 (다른 구역 파일이나 generic zone 단어 매칭 차단)
                for zc in target_zones_in_query:
                    if f"zone_{zc.lower()}" in src.lower() or f"zone_{zc.upper()}" in src.lower():
                        is_matched_critical_zone = True
                        break
            
            # [토픽별 핵심 수칙 강제 보존 바이패스]
            # 질문에 특정 대형 토픽(아파트, 숨/CPR)이 명시된 경우 관련 핵심 수본들을 단일 소스 집중 필터와 무관하게 보존합니다.
            is_critical_topic_source = False
            if "아파트" in query and "아파트" in src:
                is_critical_topic_source = True
            elif any(k in query for k in ["숨", "CPR", "심폐", "응급"]) and any(k in src.lower() for k in ["119", "응급", "cpr", "saver"]):
                is_critical_topic_source = True
            
            if src in winner_sources or is_matched_critical_zone or is_critical_topic_source:
                final_docs.append(d)

        
        # 6. 검색 의도(Intent) 기반 Lexical 리랭킹 (실전 vs 연습 구분)
        is_medical_query = any(k in query.lower() for k in ["cpr", "심폐", "소생", "압박", "의식", "호흡", "지혈", "출혈", "골절", "부목", "상처", "응급"])
        
        if is_medical_query:
            intent_keywords = ["소생술", "cpr", "압박", "의식", "호흡", "지혈", "출혈", "골절", "부목", "상처", "인공호흡"]
            # 대피용 키워드는 의료 쿼리에서 페널티 키워드로 동작하도록 보완
            evac_keywords = [
                "대피", "요령", "행동", "즉시", "절대", "대처", "수건", "자세", "비상", "경고", "피난",
                "차단기", "밸브", "누출", "화학물질", "폭발", "배전반", "가스", "환기", "밀폐", "방독면", "전원"
            ]
            penalty_keywords = ["연습", "계획", "수립", "캠페인", "교육", "훈련", "조사", "참여", "안내서"] + evac_keywords
        else:
            intent_keywords = [
                "대피", "요령", "행동", "즉시", "절대", "대처", "수건", "자세", "비상", "경고", "피난",
                "차단기", "밸브", "누출", "화학물질", "폭발", "배전반", "가스", "환기", "밀폐", "방독면", "전원"
            ]
            penalty_keywords = ["연습", "계획", "수립", "캠페인", "교육", "훈련", "조사", "참여", "안내서"]
            
        is_action_query = any(k in query.lower() for k in ["대처", "요령", "방법", "어떻게", "방안", "행동", "가이드"])
        
        reranked_docs = []
        for i, d in enumerate(final_docs):
            base_score = 100 - i  # RRF 순위에 기반한 기본 스코어
            feature_score = 0
            content = d.get('page_content', '')
            src = d.get('source', '').lower()
            
            # --- 고도화된 리랭킹 필터 ---
            
            # 1. 소스 파일명 및 Zone 구역 매칭 보너스 (+80점 - 최우선 순위 격상)
            for kw in ["공장", "factory", "아파트", "apartment", "화산", "태풍"]:
                if kw in query.lower() and kw in src:
                    feature_score += 25
                    
            for zone_char in ["A", "B", "C"]:
                if f"{zone_char}구역" in query or f"{zone_char} 구역" in query or f"zone_{zone_char.lower()}" in query or f"zone_{zone_char.upper()}" in query:
                    if f"zone_{zone_char.lower()}" in src or f"zone_{zone_char.upper()}" in src:
                        feature_score += 80  # 최상위로 끌어올림
            
            if is_action_query:
                # 2. 행동 강령에 자주 나오는 핵심 실전 키워드 가점 부여 (+10점)
                feature_score += sum(10 for kw in intent_keywords if kw in content)
                # 3. 매뉴얼 서문 및 훈련 파트에 자주 나오는 키워드 강력 감점 (-25점)
                feature_score -= sum(25 for kw in penalty_keywords if kw in content)
                
            reranked_docs.append((base_score + feature_score, d))
            
        # 재계산된 점수 기준 내림차순 정렬
        reranked_docs.sort(key=lambda x: x[0], reverse=True)
        super_final_docs = [d for score, d in reranked_docs]
        
        # 7. BGE Reranker를 통한 2차 시맨틱 정밀 리랭킹 및 Lexical 가중치 융합
        if self.reranker is not None and super_final_docs:
            try:
                # 엣지 CPU 오버헤드 방지를 위해 최정예 후보 10개 컷오프
                candidates = super_final_docs[:10]
                pairs = [[query, doc.get("page_content", "")] for doc in candidates]
                
                # 시맨틱 가중치 계산
                bge_scores = self.reranker.predict(pairs)
                
                hybrid_candidates = []
                for bge_score, doc in zip(bge_scores, candidates):
                    # Lexical 점수 가져오기 (reranked_docs에서 doc의 score 매칭)
                    lex_score = next((score for score, d in reranked_docs if d == doc), 0.0)
                    norm_lex = lex_score / 100.0
                    
                    # 신고 예시/템플릿처럼 실제 대처 지침이 아닌 단순 템플릿(00동, 00구, 안내 ▶) 감지 시 강력한 페널티 부여
                    reporting_penalty = 0.0
                    content = doc.get("page_content", "")
                    if any(w in content for w in ["00동", "00구", "사상자여부", "안내 ▶", "위치 ▶", "피해 ▶"]):
                        reporting_penalty = -0.5
                        
                    combined_score = bge_score + (norm_lex * 0.2) + reporting_penalty
                    hybrid_candidates.append((combined_score, doc))
                
                # 최종 융합 점수 기준 내림차순 정렬
                hybrid_candidates.sort(key=lambda x: x[0], reverse=True)
                final_sorted_docs = [doc for _, doc in hybrid_candidates]
                
                return final_sorted_docs[:getattr(config, 'RAG_TOP_K', 4)]
            except Exception as e:
                print(f"[NativeRAG] Reranker 추론 실패 (Lexical Fallback 가동): {e}")
                return super_final_docs[:getattr(config, 'RAG_TOP_K', 4)]
        
        return super_final_docs[:getattr(config, 'RAG_TOP_K', 4)] # 속도와 품질의 타협점인 4개로 지식 전달량 조정

# 싱글톤 인스턴스 제공
rag_manager = NativeRAGManager()
