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
    data/ 폴더의 모든 매뉴얼(JSON + TXT)을 통합 로딩하고 청킹합니다.
    """
    data_dir = config.DATA_DIR
    all_chunks = []

    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    # 1. JSON 형태의 미리 청킹된 파일 로드 (주요 소방 매뉴얼)
    json_path = os.path.join(data_dir, "chunked_manuals.json")
    if os.path.exists(json_path):
        print(f"📖 JSON 매뉴얼 데이터({json_path})를 통합 로드합니다.")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for item in data:
            doc = Document(
                page_content=item.get("content", ""),
                metadata={"source": item.get("source", "Unknown"), "title": item.get("title", "")}
            )
            all_chunks.append(doc)
        print(f"✅ JSON 데이터 로드 완료: {len(data)}개 청크 수집")

    # 2. 추가 TXT 파일 로드 (새로 추가된 매뉴얼 등)
    txt_files = glob.glob(os.path.join(data_dir, "**/*.txt"), recursive=True)
    if txt_files:
        print(f"📄 추가 텍스트 문서 {len(txt_files)}개를 감지했습니다.")
        # DirectoryLoader를 통해 모든 txt 파일 로드
        loader = DirectoryLoader(data_dir, glob="**/*.txt", loader_cls=TextLoader,
                                 loader_kwargs={"encoding": "utf-8"})
        documents = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )
        txt_chunks = splitter.split_documents(documents)
        all_chunks.extend(txt_chunks)
        print(f"✅ 텍스트 데이터 분할 완료: {len(txt_chunks)}개 청크 추가")

    if not all_chunks:
        print(f"⚠️ {data_dir}/ 폴더에 로드할 수 있는 지식이 없습니다.")
        return []

    print(f"🚀 통합 데이터 준비 완료: 총 {len(all_chunks)}개 청크 준비됨")
    return all_chunks
