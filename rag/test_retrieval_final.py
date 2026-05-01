import os
import sys
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
import config

def test_retrieval(query):
    print(f"\n[Search] Query: {query}")
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    embeddings = OllamaEmbeddings(model=config.EMBEDDING_MODEL, base_url=ollama_host)
    db = Chroma(persist_directory=config.VECTORDB_DIR, embedding_function=embeddings)
    
    docs = db.similarity_search(query, k=5)
    
    sources = set([os.path.basename(doc.metadata.get('source', 'unknown')) for doc in docs])
    print(f"[*] Retrieved from {len(docs)} chunks.")
    print(f"[*] Sources found: {sources}")
    return sources

if __name__ == "__main__":
    # 인코딩 안전을 위해 한국어를 변수에 담아 전달
    factory_q = "공장 화재 시 대처법"
    apartment_q = "아파트 화재 시 대처법"
    
    factory_sources = test_retrieval(factory_q)
    apartment_sources = test_retrieval(apartment_q)
    
    print("\n" + "="*50)
    print("RESULT ANALYSIS")
    if "test_manual.txt" in factory_sources:
        print("SUCCESS: Factory manual found for factory query!")
    else:
        print("FAIL: Factory manual NOT found for factory query.")
        
    if factory_sources != apartment_sources:
        print("SUCCESS: Search results are DIFFERENT for different locations!")
    else:
        print("WARNING: Search results are still the same.")
    print("="*50)
