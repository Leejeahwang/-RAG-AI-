import json

# --- 1. RAG 최적화: 계층적 재귀 스플리터 (Recursive Splitter) ---
def recursive_chunk_text(text, separators=["\n\n", "\n", ". ", " "], chunk_size=500, overlap=100):
    """
    최대한 의미 기반으로 자르기 위해 구분자(Separator)를 순차적으로 적용합니다.
    """
    final_chunks = []
    
    def split_recursive(content, current_seps):
        if len(content) <= chunk_size:
            return [content]
        
        if not current_seps:
            # 더 이상 나눌 구분자가 없으면 강제로 자름
            return [content[i:i + chunk_size] for i in range(0, len(content), chunk_size - overlap)]
        
        sep = current_seps[0]
        remaining_seps = current_seps[1:]
        
        # 구분자로 쪼갬
        parts = content.split(sep)
        temp_chunks = []
        current_chunk = ""
        
        for part in parts:
            if current_chunk and len(current_chunk) + len(part) + len(sep) > chunk_size:
                # 다음 조각을 붙였을 때 사이즈 초과 시, 지금까지 모은 걸 저장
                temp_chunks.append(current_chunk.strip())
                # Overlap 계산: 현재 조각의 끝부분을 조금 가져옴
                overlap_text = current_chunk[-(overlap):] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + sep + part
            else:
                if current_chunk:
                    current_chunk += sep + part
                else:
                    current_chunk = part
                    
        if current_chunk:
            temp_chunks.append(current_chunk.strip())
            
        # 너무 큰 조각이 남았다면 다음 구분자로 더 잘게 쪼갬
        result = []
        for chunk in temp_chunks:
            if len(chunk) > chunk_size:
                result.extend(split_recursive(chunk, remaining_seps))
            elif len(chunk) > 20: # 너무 작은 조각 무시
                result.append(chunk)
        return result

    return split_recursive(text, separators)

# --- 2. 파싱된 JSON 데이터 불러오기 ---
file_name = "parsed_manuals.json"

print("RAG(검색 증강 생성) 최적화를 시작합니다...\n")

try:
    with open(file_name, "r", encoding="utf-8") as f:
        documents = json.load(f)
except FileNotFoundError:
    print(f"앗! '{file_name}' 파일이 없습니다. parsing.py를 먼저 실행해주세요!")
    exit()

chunked_data = []

# --- 3. 재귀적 쪼개기 및 문맥(Context) 강화 ---
for doc in documents:
    source_name = doc["source"]
    content = doc["content"]
    print(f"[{source_name}] 고품질 재귀적 청킹 작업 중...")
    
    # 문맥 강화를 위해 파일명 정보를 각 청크에 주입 준비
    doc_context = f"[출처: {source_name}]\n"
    
    # 500자 단위, 재귀적 스플릿 적용
    smart_chunks = recursive_chunk_text(content, chunk_size=500, overlap=100)
    
    chunk_id = 1
    for chunk in smart_chunks:
        # 각 청크의 머리에 문서 정보를 붙여 AI가 길을 잃지 않게 함
        enriched_content = doc_context + chunk
        
        chunked_data.append({
            "source": source_name,
            "chunk_id": chunk_id,
            "content": enriched_content
        })
        chunk_id += 1

# --- 4. RAG용 고품질 결과물 저장 ---
save_path = "chunked_manuals.json"
with open(save_path, "w", encoding="utf-8") as f:
    json.dump(chunked_data, f, ensure_ascii=False, indent=4)

print(f"\n완료! 단어 스플릿 없이, 문맥이 부드럽게 이어지는 총 {len(chunked_data)}개의 최고급 RAG 조각들이 '{save_path}'에 저장되었습니다!")

# 썰린 조각 미리보기 (겹침 현상 확인)
if len(chunked_data) >= 2:
    print("--------------------------------------------------")
    print(f"  [미리보기 - 1번 조각] (출처: {chunked_data[0]['source']})")
    # 앞부분만 살짝 출력 (긴 경우 한 줄 처리 방지)
    print(f"{chunked_data[0]['content'][:200]} ... [생략]\n")
    print(f"  [미리보기 - 2번 조각 (100자 겹침 확인)] (출처: {chunked_data[1]['source']})")
    print(f"{chunked_data[1]['content'][:200]} ... [생략]")
    print("--------------------------------------------------")