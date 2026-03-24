"""
RAG (Retrieval-Augmented Generation) 모듈
- loader: 문서 로딩 & 청킹
- retriever: 벡터DB 생성 & 검색
- chain: QA 체인 & 프롬프트
"""

from rag.loader import load_and_split
from rag.retriever import build_vectorstore, get_retriever
from rag.chain import build_qa_chain
