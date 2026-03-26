"""
문서 로딩 & 청킹 모듈 (승훈님 담당)
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from typing import List
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import config  # 전역 설정 파일

# ==========================================
# 1. 스마트 로그 설정 (라즈베리파이 최적화)
# ==========================================
log_handler = RotatingFileHandler(
    "edge_saver.log", 
    maxBytes=1024 * 1024 * 5,  
    backupCount=3,             
    encoding="utf-8"
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        log_handler,
        logging.StreamHandler() 
    ]
)
logger = logging.getLogger(__name__)

# ==========================================
# 2. 문서 로드 및 전처리 클래스
# ==========================================
class EdgeLoader:
    """
    매뉴얼 데이터를 로드하고 AI 최적화 형태로 분할하는 클래스.
    데이터 노이즈 방지 및 시스템 안정성 기능을 포함합니다.
    """
    def __init__(self):
        # config.py에서 설정값 안전하게 가져오기
        self.data_dir = getattr(config, "DATA_DIR", "./data")
        self.chunk_size = getattr(config, "CHUNK_SIZE", 400)
        self.chunk_overlap = getattr(config, "CHUNK_OVERLAP", 50)
        
        # 한국어 문맥 유지에 특화된 가위(Splitter) 설정
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len
        )

    def _prepare_directory(self):
        """데이터 저장 폴더가 없으면 자동으로 생성"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            logger.info(f"📁 매뉴얼 폴더 생성됨: {self.data_dir}")

    def load_and_split(self) -> List[Document]:
        
        self._prepare_directory()

        try:
            logger.info(f"📂 매뉴얼 데이터 수집 중... (위치: {self.data_dir})")
            loader = DirectoryLoader(
            self.data_dir,          
            glob="*.txt",           
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"}
            )     

            documents = loader.load()

            if not documents:
                logger.warning(f"⚠️ {self.data_dir} 폴더에 .txt 파일이 하나도 없습니다.")
                return []

            chunks = self.splitter.split_documents(documents)
            
            logger.info(f"✅ 완료: {len(documents)}개 파일 처리 -> {len(chunks)}개 조각 생성")
            return chunks

        except Exception as e:
            logger.error(f"❌ 데이터 처리 중 치명적 오류 발생: {str(e)}")
            return []
