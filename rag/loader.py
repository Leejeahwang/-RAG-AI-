"""
문서 로딩 & 청킹 모듈 (승훈님 담당)
"""

from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import config
import os


def load_and_split():
    """
    data/ 폴더의 매뉴얼 문서를 로딩하고 청킹합니다.

    Returns:
        list: 청킹된 Document 리스트
    """
    data_dir = config.DATA_DIR

    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    # txt 파일이 있으면 로드
    txt_files = [f for f in os.listdir(data_dir) if f.endswith('.txt')]
    if not txt_files:
        print(f"⚠️ {data_dir}/ 폴더에 매뉴얼 파일이 없습니다.")
        print("   → data/ 폴더에 소방 매뉴얼 txt 파일을 넣어주세요.")
        return []

    loader = DirectoryLoader(data_dir, glob="**/*.txt", loader_cls=TextLoader,
                             loader_kwargs={"encoding": "utf-8"})
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(documents)
    print(f"✅ {len(documents)}개 문서 → {len(chunks)}개 청크로 분할 완료")
    return chunks
