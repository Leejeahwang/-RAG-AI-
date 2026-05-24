import os
import sys
from langchain_ollama import OllamaEmbeddings

def check_dimension(model_name):
    print(f"\n[Check] Testing model: {model_name}")
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    
    try:
        embeddings = OllamaEmbeddings(
            model=model_name,
            base_url=ollama_host
        )
        
        test_text = "Hello, dimension test."
        vector = embeddings.embed_query(test_text)
        
        print(f"[*] Success! Dimension: {len(vector)}")
        return len(vector)
    except Exception as e:
        print(f"[!] Failed: {e}")
        return None

if __name__ == "__main__":
    check_dimension("nomic-embed-text")
    check_dimension("bge-m3:latest")
    check_dimension("mxbai-embed-large")
