"""
PDF 파싱 모듈 (종화님 담당)

Phase 1 작업 내용:
- 적십자 매뉴얼 PDF 파싱 (PyMuPDF 사용)
- 스마트 청킹 (제목 기준 300~500자 단위)
- FAISS 인덱스 영구 저장/로드

설치:
    pip install pymupdf
"""

# TODO (종화님):
# 1. PyMuPDF(fitz)로 PDF 파일을 읽어 텍스트 추출
# 2. 제목/섹션 기준으로 스마트 청킹 (300~500자 단위)
# 3. 메타데이터(페이지 번호, 섹션명) 포함하여 Document 객체 생성


def parse_pdf(pdf_path: str) -> list:
    """
    PDF 파일을 파싱하여 청크 리스트를 반환합니다.

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        list: Document 객체 리스트 (텍스트 + 메타데이터)

    TODO (종화님):
        - PyMuPDF(fitz)를 사용하여 PDF 텍스트 추출
        - 제목 기준 스마트 청킹 구현
        - 메타데이터(페이지번호, 섹션명) 추가
    """
    raise NotImplementedError("PDF 파싱 모듈이 아직 구현되지 않았습니다.")
