"""
벡터DB 생성 & 검색 모듈 (승훈님 담당)
"""

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
import config


import os
import shutil

def build_vectorstore(chunks):
    """청크를 벡터DB에 저장합니다."""
    # 기존 DB가 있다면 삭제하여 중복 문서 적재를 방지 (DB 초기화)
    if os.path.exists(config.VECTORDB_DIR):
        print(f"[시스템] 기존 벡터DB 삭제 중... ({config.VECTORDB_DIR})")
        shutil.rmtree(config.VECTORDB_DIR)

    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    embeddings = OllamaEmbeddings(model=config.EMBEDDING_MODEL, base_url=ollama_host)
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
