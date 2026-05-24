import os
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
import config

def debug_database():
    print("=== [DATABASE DEBUG] ===")
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    embeddings = OllamaEmbeddings(model=config.EMBEDDING_MODEL, base_url=ollama_host)
    db = Chroma(persist_directory=config.VECTORDB_DIR, embedding_function=embeddings)
    
    data = db.get()
    all_ids = data['ids']
    all_docs = data['documents']
    all_metas = data['metadatas']
    
    print(f"[*] Total entries in DB: {len(all_ids)}")
    
    test_manual_entries = []
    for doc, meta in zip(all_docs, all_metas):
        source = meta.get('source', '')
        if 'test_manual' in source:
            test_manual_entries.append((source, doc))
            
    print(f"[*] Found {len(test_manual_entries)} chunks matching 'test_manual'")
    
    if test_manual_entries:
        for i, (src, content) in enumerate(test_manual_entries[:5]):
            print(f"\n--- Chunk #{i+1} (Source: {src}) ---")
            print(f"Preview: {content[:150]}")
            if not content.strip():
                print("!!!! WARNING: THIS CHUNK IS EMPTY !!!!")
    else:
        print("!!!! CRITICAL: test_manual.txt is MISSING from DB !!!!")

if __name__ == "__main__":
    debug_database()
