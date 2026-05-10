"""
벡터DB 생성 & 검색 모듈 (승훈님 담당)
"""

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
import config


import os
import shutil

def build_vectorstore(chunks):
    """청크를 벡터DB에 저장하거나 기존 DB를 로드합니다."""
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    embeddings = OllamaEmbeddings(model=config.EMBEDDING_MODEL, base_url=ollama_host)

    # 기존 DB가 있다면 재생성(임베딩 연산)하지 않고 바로 불러옵니다.
    if os.path.exists(config.VECTORDB_DIR) and os.listdir(config.VECTORDB_DIR):
        print(f"[시스템] 기존 벡터DB 로드 중... ({config.VECTORDB_DIR})")
        db = Chroma(
            persist_directory=config.VECTORDB_DIR, 
            embedding_function=embeddings
        )
        print(f"✅ 기존 벡터DB 로드 완료")
        return db

    print(f"[시스템] 새 벡터DB 구축 중... (1~3분 소요)")
    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=config.VECTORDB_DIR,
    )
    print(f"✅ 벡터DB 구축 완료 ({config.VECTORDB_DIR}/)")
    return db


def get_retriever(db, top_k=5):
    """벡터DB에서 유사도 검색기를 반환합니다."""
    return db.as_retriever(search_kwargs={"k": top_k})
