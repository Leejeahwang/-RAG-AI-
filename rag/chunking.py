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
    """
    텍스트를 의미 있는 단위로 재귀적으로 분할합니다.
    """
    final_chunks = []
    
    def split_recursive(content, current_seps):
        # 1. 대상 텍스트가 이미 목표 크기보다 작으면 그대로 반환
        if len(content) <= chunk_size:
            return [content]
        
        # 2. 더 이상 쓸 수 있는 구분자가 없으면 글자 수대로 강제 분할
        if not current_seps:
            return [content[i:i + chunk_size] for i in range(0, len(content), chunk_size - overlap)]
        
        sep = current_seps[0]
        remaining_seps = current_seps[1:]
        
        # 3. 현재 구분자로 텍스트 나누기
        parts = content.split(sep)
        temp_chunks = []
        current_chunk = ""
        
        for part in parts:
            # 현재 조각을 붙였을 때 크기를 넘어가면 지금까지의 덩어리를 저장
            if current_chunk and len(current_chunk) + len(part) + len(sep) > chunk_size:
                temp_chunks.append(current_chunk.strip())
                # 중첩(Overlap)을 위해 끝부분 일부를 다음 조각의 시작으로 사용
                overlap_text = current_chunk[-(overlap):] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + sep + part
            else:
                if current_chunk:
                    current_chunk += sep + part
                else:
                    current_chunk = part
                    
        if current_chunk:
            temp_chunks.append(current_chunk.strip())
            
        # 4. 분할된 각 조각이 여전히 크면 다음 구분자로 재귀 호출
        result = []
        for chunk in temp_chunks:
            if len(chunk) > chunk_size:
                result.extend(split_recursive(chunk, remaining_seps))
            elif len(chunk) > 50:  # [개선] 50자 미만의 노이즈성 데이터는 걸러냄 (기존 20자)
                result.append(chunk)
        return result

    return split_recursive(text, separators)

# --- 2. 설정 ---
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
    
    # [개선] 문서의 첫 줄을 제목(Title)으로 취급하여 모든 청크에 명시
    first_line = content.split('\n')[0].strip()[:50]
    title = first_line if len(first_line) > 5 else source_name
    
    print(f"[처리 중] {source_name}: 텍스트 분할 중...")
    
    # 500자 단위, 100자 중첩 청킹
    smart_chunks = recursive_chunk_text(content, chunk_size=500, overlap=100)
    
    chunk_id = 1
    for chunk in smart_chunks:
        # [개선] AI가 제목과 본문을 확실히 구분하도록 포맷 개선
        enriched_content = f"## 주제: {title}\n(출처: {source_name})\n\n{chunk}"
        
        chunked_data.append({
            "source": source_name,
            "title": title,
            "chunk_id": chunk_id,
            "content": enriched_content
        })
        chunk_id += 1

# --- 4. 결과 내보내기 ---
save_path = os.path.join(project_root, "data", "chunked_manuals.json")
with open(save_path, "w", encoding="utf-8") as f:
    json.dump(chunked_data, f, ensure_ascii=False, indent=4)

print(f"\n[정보] 청킹 완료. {len(chunked_data)}개의 유의미한 청크가 '{save_path}'에 저장되었습니다.")

# 출력 미리보기
if chunked_data:
    print("-" * 60)
    print(f"  [청크 미리보기 #1] ({chunked_data[0]['source']})")
    print("-" * 60)
    print(f"{chunked_data[0]['content'][:300]} ...")
    print("-" * 60)