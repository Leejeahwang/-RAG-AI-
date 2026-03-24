"""
문서 로딩 & 청킹 모듈
- 현재: TXT 파일 로딩 (TextLoader)
- 향후: PDF 파싱으로 확장 예정 (승훈님 담당, PyMuPDF 사용)
"""

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config


def load_and_split(file_path: str = None) -> list:
    """
    매뉴얼 파일을 로드하고 청크 단위로 분할합니다.

    Args:
        file_path: 매뉴얼 파일 경로 (기본값: config.MANUAL_PATH)

    Returns:
        list: 분할된 Document 객체 리스트
    """
    if file_path is None:
        file_path = config.MANUAL_PATH

    loader = TextLoader(file_path, encoding="utf-8")
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )
    chunks = text_splitter.split_documents(docs)

    print(f"📦 문서 로딩 완료: {len(chunks)}개 청크 생성")
    return chunks
