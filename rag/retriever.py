"""
벡터DB 생성 & 검색 모듈 (승훈님 담당)
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from typing import List
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document
import config

# 로깅 설정 (SD 카드 보호 및 시스템 추적용)
log_handler = RotatingFileHandler(
    "edge_saver.log", 
    maxBytes=1024 * 1024 * 5, 
    backupCount=3, 
    encoding="utf-8"
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[log_handler, logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class EdgeRetriever:
    """
    라즈베리파이 최적화 벡터 검색 엔진.
    데이터 저장과 검색기 반환 기능만 제공하는 실전용 클래스입니다.
    """
    def __init__(self):
        # config.py 설정값 로드
        self.db_dir = getattr(config, "VECTORDB_DIR", "chroma_db")
        self.model_name = getattr(config, "EMBEDDING_MODEL", "qwen2.5:1.5b")
        
        # 임베딩 모델(번역기) 초기화
        self.embeddings = OllamaEmbeddings(model=self.model_name)
        self.vectorstore = None

    def _load_database(self) -> bool:
        """기존 DB가 존재하면 로드"""
        if os.path.exists(self.db_dir):
            try:
                self.vectorstore = Chroma(
                    persist_directory=self.db_dir,
                    embedding_function=self.embeddings
                )
                logger.info(f"📂 기존 지식 창고 로드 완료: {self.db_dir}")
                return True
            except Exception as e:
                logger.error(f"❌ DB 로드 실패: {e}")
        return False

    def build_vectorstore(self, chunks: List[Document]):
        """[실행] 전달받은 청크를 벡터 DB에 물리적으로 저장"""
        if not chunks:
            logger.warning("⚠️ 저장할 청크가 없습니다.")
            return None

        try:
            logger.info(f"📦 '{self.db_dir}'에 지식 저장 시작...")
            self.vectorstore = Chroma.from_documents(
                documents=chunks,
                embedding=self.embeddings,
                persist_directory=self.db_dir,
            )
            logger.info("✅ 지식 저장 완료!")
            return self.vectorstore
        except Exception as e:
            logger.error(f"❌ 지식 저장 오류: {str(e)}")
            return None

    def get_retriever(self, top_k: int = 3):
        """[연결] AI 답변기(chain.py)용 검색 인터페이스 반환"""
        if self.vectorstore is None:
            if not self._load_database():
                logger.error("❌ 저장된 지식이 없습니다. build를 먼저 실행하세요.")
                return None

        return self.vectorstore.as_retriever(search_kwargs={"k": top_k})
