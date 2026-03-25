"""
벡터DB 생성 & 검색 모듈 (승훈님 담당)
"""

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
import config


def build_vectorstore(chunks):
    """청크를 벡터DB에 저장합니다."""
    embeddings = OllamaEmbeddings(model=config.EMBEDDING_MODEL)
    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=config.VECTORDB_DIR,
    )
    print(f"✅ 벡터DB 구축 완료 ({config.VECTORDB_DIR}/)")
    return db


def get_retriever(db, top_k=3):
    """벡터DB에서 유사도 검색기를 반환합니다."""
    return db.as_retriever(search_kwargs={"k": top_k})
