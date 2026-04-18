"""
벡터DB 생성 & 검색 모듈 (승훈님 담당)
"""

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
import config


import os

def build_vectorstore(chunks=None):
    """청크를 벡터DB에 저장하거나, 기존 DB를 로드합니다."""
    import shutil
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    embeddings = OllamaEmbeddings(model=config.EMBEDDING_MODEL, base_url=ollama_host)
    
    db_path = config.VECTORDB_DIR
    db_exists = os.path.exists(db_path) and os.listdir(db_path)
    
    if db_exists:
        try:
            db = Chroma(
                persist_directory=db_path,
                embedding_function=embeddings
            )
            count = db._collection.count()
            if count > 0:
                print(f"📦 기존 벡터DB를 로드합니다. (데이터 개수: {count}개)")
                return db
            else:
                print("⚠️ 벡터DB가 비어 있습니다. 재구축을 시작합니다...")
        except Exception as e:
            print(f"⚠️ 벡터DB 로드 중 오류 발생 ({e}). 재구축을 시작합니다...")
            if os.path.exists(db_path):
                shutil.rmtree(db_path) # 손상된 폴더 삭제

    # 로드 실패하거나 데이터가 0개인 경우 -> 재구축
    if chunks is None:
        from rag.loader import load_and_split
        print("[시스템] 재구축을 위해 데이터를 새로 로딩합니다...")
        chunks = load_and_split()
        
    if not chunks:
        raise ValueError("벡터DB를 구축할 데이터(chunks)가 없습니다.")
        
    print(f"🚀 새로운 벡터DB를 구축합니다. ({len(chunks)}개 청크)")
    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=db_path,
    )
    print(f"✅ 벡터DB 구축 및 저장 완료 (데이터 개수: {db._collection.count()}개)")
    
    return db



from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_core.prompts import PromptTemplate

# 다중 쿼리 생성을 위한 프롬프트 (기술적 상세 수치 검색 최적화)
QUERY_PROMPT = PromptTemplate(
    input_variables=["question"],
    template="""당신은 소방 안전 및 매뉴얼 검색 전문가입니다.
사용자의 질문에 대해 매뉴얼의 '표(Table)', '수치(㎡, m, 개수)', '설치 기준'을 정확히 찾기 위해 3개의 기술적인 검색용 쿼리를 한국어로 작성하세요.

질문 예시: "소화기 설치 기준" -> 쿼리: "수동식 소화기 설치 대상 면적 수치", "소화기구 설치 간격 및 기준", "소방 시설 설치 규정 표"

원본 질문: {question}

출력 형식 (쿼리만 출력):
1. 
2. 
3. """,
)

def get_retriever(db, llm=None, top_k=3):
    """
    벡터DB에서 다중 쿼리 검색기를 반환하며, 검색 지능을 강화합니다.
    - 속도 최적화를 위해 top_k를 3으로 조정하고 일반 similarity 검색 사용
    """
    # 기본 검색기 설정 (속도 중심의 similarity 검색)
    base_retriever = db.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": top_k
        }
    )
    
    if llm:
        print(f"[Retrieval] 지능형 Multi-Query (Top-{top_k}) 활성화")
        retriever = MultiQueryRetriever.from_llm(
            retriever=base_retriever,
            llm=llm,
            prompt=QUERY_PROMPT
        )
        return retriever
    
    return base_retriever
