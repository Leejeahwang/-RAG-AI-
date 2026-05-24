
import os
import sys
import json
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings

# 인코딩 강제 설정
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def final_verify():
    print("=== [v7.1 정화 작업 최종 검증] ===")
    
    # 설정 로드
    persist_directory = "chroma_db"
    embedding_model = "mxbai-embed-large"
    
    embeddings = OllamaEmbeddings(model=embedding_model)
    vectorstore = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
    
    # 테스트 1: 공장 화재 관련 검색 (Factory)
    query_1 = "공장 화재 발생 시 대응 수칙"
    print(f"\n[테스트 1] 검색어: '{query_1}'")
    results_1 = vectorstore.similarity_search(query_1, k=2)
    
    for i, res in enumerate(results_1):
        print(f"  - 결과 {i+1} 출처: {res.metadata.get('source')}")
        print(f"  - 본문 일부: {res.page_content[:150]}...")

    # 테스트 2: 아파트 화재 관련 검색 (Apartment)
    query_2 = "아파트 입주자 피난 행동 요령"
    print(f"\n[테스트 2] 검색어: '{query_2}'")
    results_2 = vectorstore.similarity_search(query_2, k=2)
    
    for i, res in enumerate(results_2):
        print(f"  - 결과 {i+1} 출처: {res.metadata.get('source')}")
        print(f"  - 본문 일부: {res.page_content[:150]}...")

if __name__ == "__main__":
    final_verify()
