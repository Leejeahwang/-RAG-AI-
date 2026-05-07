"""
Native RAG 엔진 (v30)
Ollama/Chroma 의존성 없이 FAISS와 Sentence-Transformers를 직접 사용하여 
호환성과 속도를 극대화한 검색 모듈입니다.
"""

import os
import numpy as np
import faiss
import pickle
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import config
from collections import Counter

class NativeRAGManager:
    def __init__(self):
        self.model = None
        self.index = None
        self.metadata = []
        self.model_name = config.NATIVE_EMBEDDING_MODEL
        self.index_dir = config.FAISS_INDEX_DIR
        self.index_file = os.path.join(self.index_dir, "index.faiss")
        self.meta_file = os.path.join(self.index_dir, "metadata.pkl")

    def load_resources(self):
        """임베딩 모델 및 FAISS 인덱스 로드"""
        print(f"[NativeRAG] 모델 로드 중: {self.model_name}...")
        self.model = SentenceTransformer(self.model_name)
        
        if os.path.exists(self.index_file) and os.path.exists(self.meta_file):
            print(f"[NativeRAG] 기존 인덱스 로드 중: {self.index_file}")
            self.index = faiss.read_index(self.index_file)
            with open(self.meta_file, 'rb') as f:
                self.metadata = pickle.load(f)
            print(f"[NativeRAG] 로드 완료 (데이터: {len(self.metadata)}개)")
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
        
        # 파일 저장
        if not os.path.exists(self.index_dir):
            os.makedirs(self.index_dir)
        faiss.write_index(self.index, self.index_file)
        with open(self.meta_file, 'wb') as f:
            pickle.dump(self.metadata, f)
        
        print(f"[NativeRAG] 인덱스 구축 및 저장 완료: {self.index_file}")

    def search(self, query: str, top_k: int = 25, top_n_sources: int = 3) -> List[Dict[str, Any]]:
        """지능형 필터링 및 2차 리랭킹이 포함된 고속 검색"""
        if self.index is None:
            print("[NativeRAG] 에러: 인덱스가 로드되지 않았습니다.")
            return []

        # 1. 쿼리 임베딩
        query_vec = self.model.encode([query]).astype('float32')
        
        # 2. FAISS 초기 검색
        distances, indices = self.index.search(query_vec, top_k)
        
        # 3. 주제/장소 하드 필터링 (v28 logic porting)
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
        for idx in indices[0]:
            if idx == -1: continue
            doc = self.metadata[idx]
            src = doc.get('source', 'unknown').lower()
            content = doc.get('page_content', '')[:200].lower()
            
            # 필터링 판별
            doc_theme = next((theme for theme, keywords in CONFLICT_MAP.items() if any(k in src for k in keywords) or any(k in content for k in keywords)), None)
            doc_loc = next((loc for loc, keywords in LOCATION_MAP.items() if any(k in src for k in keywords) or any(k in content for k in keywords)), None)
            
            if detected_themes and doc_theme and doc_theme not in detected_themes: continue
            if detected_locs and doc_loc and doc_loc not in detected_locs: continue
            
            valid_results.append(doc)

        if not valid_results:
            return [self.metadata[i] for i in indices[0][:1]] if indices[0].size > 0 else []

        # 4. 단일 소스 집중 (v24 logic)
        source_scores = Counter()
        for i, doc in enumerate(valid_results[:10]):
            src = doc.get('source', 'unknown')
            source_scores[src] += (10 - i)
            
        winner_sources = [s for s, score in source_scores.most_common(top_n_sources)]
        final_docs = [d for d in valid_results if d.get('source') in winner_sources]
        
        # 5. 검색 의도(Intent) 기반 Lexical 리랭킹 (실전 vs 연습 구분)
        intent_keywords = [
            "대피", "요령", "행동", "즉시", "절대", "대처", "수건", "자세", "비상", "경고", "피난",
            "차단기", "밸브", "누출", "화학물질", "폭발", "배전반", "가스", "환기", "밀폐", "방독면", "전원" # 공장/산업 특화
        ]
        penalty_keywords = ["연습", "계획", "수립", "캠페인", "교육", "훈련", "조사", "참여", "안내서", "평면도"]
        
        is_action_query = any(k in query.lower() for k in ["대처", "요령", "방법", "어떻게", "방안", "행동", "가이드"])
        
        reranked_docs = []
        for i, d in enumerate(final_docs):
            base_score = 100 - i  # 1차 FAISS 유사도에 따른 기본 순위 점수 배점
            feature_score = 0
            content = d.get('page_content', '')
            src = d.get('source', '').lower()
            
            # --- 고도화된 리랭킹 필터 ---
            
            # 1. 소스 파일명 매칭 보너스: 질문의 핵심 키워드가 파일명에 있으면 강력 가점 (+25점)
            # 예: "공장 화재" 질문인데 파일명이 "factory_fire_manual"이면 우선순위 급상승
            for kw in ["공장", "factory", "아파트", "apartment", "화산", "태풍"]:
                if kw in query.lower() and kw in src:
                    feature_score += 25
            
            if is_action_query:
                # 2. 행동 강령에 자주 나오는 핵심 실전 키워드 가점 부여 (+10점)
                feature_score += sum(10 for kw in intent_keywords if kw in content)
                # 3. 매뉴얼 서문 및 훈련 파트에 자주 나오는 키워드 강력 감점 (-25점)
                feature_score -= sum(25 for kw in penalty_keywords if kw in content)
                
            reranked_docs.append((base_score + feature_score, d))
            
        # 재계산된 점수 기준 내림차순 정렬
        reranked_docs.sort(key=lambda x: x[0], reverse=True)
        super_final_docs = [d for score, d in reranked_docs]
        
        return super_final_docs[:6] # 기술적 상세 답변을 위해 컨텍스트 제공량을 6개로 확대

# 싱글톤 인스턴스 제공
rag_manager = NativeRAGManager()
