import json
import os
import sys
import re
import requests

# UTF-8 출력 보장 (Windows/Linux 호환)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 1. AI 기반 스마트 타이틀 추출 ---
def generate_ai_title(text, filename, model="qwen2.5:1.5b"):
    """
    Ollama를 사용하여 문서의 핵심 주제를 추출합니다.
    문서당 단 1회 호출하여 고품질 메타데이터 제작.
    """
    if not text:
        return filename
    
    # 문서 앞부분 1,000자만 참조 (속도 및 토큰 제한 고려)
    sample = text[:1000]
    prompt = f"""
    당신은 재난 안전 전문 가이드 요약가입니다. 아래 텍스트를 분석하여 문서의 핵심 주제를 10자 이내의 명사형으로 출력하세요.
    파일명: {filename}
    내용: {sample}
    ---
    결과(제목만 출력):
    """
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False
            }
        )
        ai_title = response.json().get("response", "").strip()
        # 불필요한 따옴표나 마크다운 기호 제거
        ai_title = re.sub(r'["\'#\.\(\)]', '', ai_title)
        return ai_title if ai_title else filename
    except Exception as e:
        print(f"  [오류] AI 타이틀 추출 실패 ({filename}): {e}")
        return filename

# --- 2. 재귀적 텍스트 분할기 (Context Awareness) ---
def recursive_chunk_text(text, separators=["\n\n", "\n", ". ", " "], chunk_size=500, overlap=100):
    """
    텍스트를 의미 있는 단위로 재귀적으로 분할하여 정보 소실을 방지합니다.
    """
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
            elif len(chunk) > 50:  # 50자 미만의 노이즈성 데이터는 제외
                result.append(chunk)
        return result

    return split_recursive(text, separators)

# --- 2.5 가치 중심 청크 필터링 ---
def is_useful_chunk(text):
    """
    RAG 지식으로서 가치가 낮은 청크(메타데이터, 단순연락처 등)를 필터링합니다.
    """
    # 1. 길이 검사 (너무 짧으면 무의미)
    if len(text.strip()) < 60:
        return False
        
    # 2. 특수문자 비중 검사 (목차나 기호 중심 페이지 제거)
    total_len = len(text)
    alnum_len = len(re.findall(r'[가-힣a-zA-Z0-9]', text))
    if total_len > 0 and (alnum_len / total_len) < 0.6:  # 글자 비중이 60% 미만이면 노이즈로 간주
        return False
        
    # 3. 금지 키워드 검사 (발행처, 저작권, 연락처 정보 등)
    # RAG 검색 시 행동 요령보다는 메타데이터가 검색되는 것을 방지
    noise_keywords = [
        '발행처', '발행일', '발행인', '내용감수', '편집디자인', 
        '저작권', '무단 전재', '전화번호', '팩스번호', '이메일',
        'TEL', 'FAX', 'E-mail', '주소 : ', '홈페이지'
    ]
    
    match_count = 0
    for kw in noise_keywords:
        if kw in text:
            match_count += 1
            
    # 노이즈 키워드가 2개 이상 발견되면 필터링
    if match_count >= 2:
        return False
        
    return True

# --- 3. 메인 프로세스 ---
def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    input_file = os.path.join(project_root, "data", "parsed_manuals.json")
    output_file = os.path.join(project_root, "data", "chunked_manuals.json")

    print("[정보] AI 기반 스마트 청킹 프로세스 준비 중...")

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            documents = json.load(f)
    except FileNotFoundError:
        print(f"[오류] '{input_file}' 파일을 찾을 수 없습니다. parser.py를 먼저 실행하세요.")
        return

    chunked_data = []
    filtered_count = 0

    print(f"[정보] 총 {len(documents)}개 문서에 대해 주제 분석 및 분할 시작.\n")

    for doc in documents:
        source_name = doc["source"]
        content = doc["content"]
        
        # 1. AI 타이틀 생성 (문서당 1회)
        print(f"  [AI 분석] {source_name} 주제 파악 중...", end=" ", flush=True)
        doc_topic = generate_ai_title(content, source_name)
        # 파일명과 AI 주제 결합 (예: 119핸드북 - 심폐소생술 가이드)
        clean_filename = os.path.splitext(source_name)[0]
        title = f"{clean_filename} ({doc_topic})"
        print(f"-> {doc_topic}")
        
        # 2. 고성능 재귀적 청킹 수행
        smart_chunks = recursive_chunk_text(content, chunk_size=500, overlap=100)
        
        # 3. 메타데이터 보강 및 저장 (필터링 적용)
        current_doc_chunks = 0
        for i, chunk in enumerate(smart_chunks):
            # 가치 기반 필터링 적용
            if not is_useful_chunk(chunk):
                filtered_count += 1
                continue
                
            # 문맥 보강 헤더 삽입 (마크다운 형식)
            enriched_content = f"## 주제: {title}\n(출처: {source_name})\n\n{chunk}"
            
            chunked_data.append({
                "source": source_name,
                "title": title,
                "chunk_id": current_doc_chunks + 1,
                "content": enriched_content
            })
            current_doc_chunks += 1

    # 결과 파일 저장
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(chunked_data, f, ensure_ascii=False, indent=4)

    print("-" * 60)
    print(f"[정보] 청킹 완료. {len(chunked_data)}개의 유의미한 청크가 '{output_file}'에 저장되었습니다.")
    print(f"  (노이즈로 판단되어 건너뛴 청크: {filtered_count}개)")
    
    # 미리보기 출력
    if chunked_data:
        print(f"  [청크 미리보기 #1] ({chunked_data[0]['source']})")
        print("-" * 60)
        print(f"{chunked_data[0]['content'][:300]} ...")
        print("-" * 60)

if __name__ == "__main__":
    main()