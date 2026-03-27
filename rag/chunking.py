import json
import re
import os
import sys

# UTF-8 출력 보장
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 1. 재귀적 텍스트 분할기 ---
def recursive_chunk_text(text, separators=["\n\n", "\n", ". ", " "], chunk_size=500, overlap=100):
    final_chunks = []
    
    def split_recursive(content, current_seps):
        if len(content) <= chunk_size:
            return [content]
        
        if not current_seps:
            return [content[i:i + chunk_size] for i in range(0, len(content), chunk_size - overlap)]
        
        sep = current_seps[0]
        remaining_seps = current_seps[1:]
        
        parts = content.split(sep)
        temp_chunks = []
        current_chunk = ""
        
        for part in parts:
            if current_chunk and len(current_chunk) + len(part) + len(sep) > chunk_size:
                temp_chunks.append(current_chunk.strip())
                overlap_text = current_chunk[-(overlap):] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + sep + part
            else:
                if current_chunk:
                    current_chunk += sep + part
                else:
                    current_chunk = part
                    
        if current_chunk:
            temp_chunks.append(current_chunk.strip())
            
        result = []
        for chunk in temp_chunks:
            if len(chunk) > chunk_size:
                result.extend(split_recursive(chunk, remaining_seps))
            elif len(chunk) > 20: 
                result.append(chunk)
        return result

    return split_recursive(text, separators)

# --- 2. 설정 ---
# 데이터 파일은 data/ 디렉토리, 스크립트는 rag/에 위치
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

file_name = os.path.join(project_root, "data", "parsed_manuals.json")
print("[정보] 청킹 프로세스 시작 중...")

try:
    with open(file_name, "r", encoding="utf-8") as f:
        documents = json.load(f)
except FileNotFoundError:
    print(f"[오류] '{file_name}' 파일을 찾을 수 없습니다. parsing.py를 먼저 실행하세요.")
    exit()

chunked_data = []

# --- 3. 청킹 및 문맥 보강 (Context Enrichment) ---
for doc in documents:
    source_name = doc["source"]
    content = doc["content"]
    print(f"[처리 중] {source_name}: 텍스트 분할 중...")
    
    doc_context = f"[출처: {source_name}]\n"
    
    # 500자 단위, 100자 중첩 청킹
    smart_chunks = recursive_chunk_text(content, chunk_size=500, overlap=100)
    
    chunk_id = 1
    for chunk in smart_chunks:
        enriched_content = doc_context + chunk
        
        chunked_data.append({
            "source": source_name,
            "chunk_id": chunk_id,
            "content": enriched_content
        })
        chunk_id += 1

# --- 4. 결과 내보내기 ---
save_path = os.path.join(project_root, "data", "chunked_manuals.json")
with open(save_path, "w", encoding="utf-8") as f:
    json.dump(chunked_data, f, ensure_ascii=False, indent=4)

print(f"\n[정보] 청킹 종료. {len(chunked_data)}개의 청크가 '{save_path}'에 저장되었습니다.")

# 출력 미리보기
if chunked_data:
    print("-" * 50)
    print(f"  [미리보기 - 청크 #1] ({chunked_data[0]['source']})")
    print(f"{chunked_data[0]['content'][:200]} ... \n")
    if len(chunked_data) > 1:
        print(f"  [미리보기 - 청크 #2] ({chunked_data[1]['source']})")
        print(f"{chunked_data[1]['content'][:200]} ...")
    print("-" * 50)