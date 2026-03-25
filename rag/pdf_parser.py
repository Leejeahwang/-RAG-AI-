"""
PDF 파싱 모듈 (종화님 담당)

소방 매뉴얼 및 건물 도면 PDF를 텍스트로 변환합니다.
pip install pymupdf
"""


def parse_pdf(pdf_path, output_dir="data"):
    """
    PDF 파일을 파싱하여 텍스트 파일로 저장합니다.

    Args:
        pdf_path: 파싱할 PDF 파일 경로
        output_dir: 텍스트 파일 저장 위치

    Returns:
        str: 저장된 텍스트 파일 경로

    TODO (종화님):
        1. 적십자/소방청 응급처치 PDF 매뉴얼 수집
        2. PyMuPDF(fitz)로 PDF 텍스트 추출
        3. 섹션/제목 기준 스마트 분할
        4. data/ 폴더에 txt 파일로 저장
    """
    raise NotImplementedError("PDF 파싱 모듈 구현 예정")
