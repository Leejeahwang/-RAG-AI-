"""
벡터DB 생성 & 검색 모듈
- ChromaDB 기반 벡터 저장소 생성/로드
- 검색기(Retriever) 반환
"""

import os
import shutil

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings

import config


def build_vectorstore(chunks: list, force_rebuild: bool = True):
    """
    청크 리스트로부터 ChromaDB 벡터 저장소를 생성합니다.

    Args:
        chunks: Document 객체 리스트
        force_rebuild: True이면 기존 DB를 삭제하고 새로 생성

    Returns:
        Chroma: 벡터 저장소 인스턴스
    """
    if force_rebuild and os.path.exists(config.CHROMA_DB_DIR):
        shutil.rmtree(config.CHROMA_DB_DIR)

    embeddings = OllamaEmbeddings(model=config.EMBEDDING_MODEL)
    db = Chroma.from_documents(
        chunks,
        embeddings,
        persist_directory=config.CHROMA_DB_DIR,
    )

    print(f"🗄️ 벡터DB 생성 완료 ({config.CHROMA_DB_DIR})")
    return db


def get_retriever(db, top_k: int = None):
    """
    벡터 저장소에서 검색기를 생성합니다.

    Args:
        db: Chroma 벡터 저장소
        top_k: 검색할 상위 문서 수 (기본값: config.RETRIEVER_TOP_K)

    Returns:
        Retriever 인스턴스
    """
    if top_k is None:
        top_k = config.RETRIEVER_TOP_K

    return db.as_retriever(search_kwargs={"k": top_k})
