"""
문서 로딩 & 청킹 모듈 (승훈님 담당)
"""

import json
import os
import glob
from langchain_core.documents import Document
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import config

def load_and_split():
    """
    data/ 폴더의 매뉴얼 문서를 로딩하고 (필요 시) 청킹합니다.

    Returns:
        list: 청킹된 Document 리스트
    """
    data_dir = config.DATA_DIR

    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    # 1. JSON 형태의 미리 청킹된 파일이 있는지 우선 확인 (새로 가져온 데이터)
    json_path = os.path.join(data_dir, "chunked_manuals.json")
    if os.path.exists(json_path):
        print(f"📖 JSON 매뉴얼 데이터({json_path})를 로드합니다.")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        chunks = []
        for item in data:
            doc = Document(
                page_content=item.get("content", ""),
                metadata={"source": item.get("source", "Unknown"), "title": item.get("title", "")}
            )
            chunks.append(doc)
            
        print(f"✅ JSON 데이터 로드 완료: 총 {len(chunks)}개 청크")
        return chunks

    # 2. JSON이 없다면 기존 txt 파일 폴더 형식으로 진행
    txt_files = glob.glob(os.path.join(data_dir, "**/*.txt"), recursive=True)
    if not txt_files:
        print(f"⚠️ {data_dir}/ 폴더에 매뉴얼 파일이 없습니다.")
        print("   → data/ 폴더에 소방 매뉴얼 txt 또는 json 파일을 넣어주세요.")
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
