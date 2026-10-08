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

    # 2. 추가 TXT 파일 로드 (가장 견고한 수동 인코딩 시도 방식)
    txt_files = glob.glob(os.path.join(data_dir, "**/*.txt"), recursive=True)
    if txt_files:
        print(f"📄 추가 텍스트 문서 {len(txt_files)}개를 감지했습니다.")
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )

        for txt_path in txt_files:
            content = ""
            # 1순위: UTF-8 시도
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                # 2순위: CP949(EUC-KR) 시도
                try:
                    with open(txt_path, "r", encoding="cp949") as f:
                        content = f.read()
                except Exception as e:
                    print(f"⚠️ 파일 로드 실패 ({txt_path}): {e}")
                    continue
            
            if content:
                doc = Document(
                    page_content=content,
                    metadata={"source": os.path.basename(txt_path)}
                )
                txt_chunks = splitter.split_documents([doc])
                
                # [품질 향상] 각 청크 상단에 출처 정보를 주입하여 컨텍스트 보존
                for chunk in txt_chunks:
                    source_name = chunk.metadata.get("source", "알 수 없는 매뉴얼")
                    chunk.page_content = f"### [출처: {source_name}]\n\n" + chunk.page_content
                
                all_chunks.extend(txt_chunks)
        
        print(f"✅ 텍스트 데이터 통합 완료: {len(all_chunks) - (len(data) if 'data' in locals() else 0)}개 청크 추가")

    if not all_chunks:
        print(f"⚠️ {data_dir}/ 폴더에 로드할 수 있는 지식이 없습니다.")
        return []

    print(f"🚀 통합 데이터 준비 완료: 총 {len(all_chunks)}개 청크 준비됨")
    return all_chunks
