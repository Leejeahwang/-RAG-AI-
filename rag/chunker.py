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
def generate_ai_title(text, filename, model="gemma4:e2b"):
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

# --- 2. 마크다운 구조 인식형 스마트 분할기 (Structural Chunking) ---
def markdown_aware_chunking(text, title, chunk_size=800, overlap=150):
    """
    마크다운 헤더(#, ##, ###)를 인식하여 의미 단위로 분할합니다.
    각 청크 상단에 문서 구조(Breadcrumbs)를 삽입하여 문맥을 보존합니다.
    """
    # 헤더 기준으로 분할 (헤더 자체도 보존)
    sections = re.split(r'(^#{1,4} .+)', text, flags=re.MULTILINE)
    
    chunks = []
    current_breadcrumbs = [title]
    current_content = ""
    
    # 헤더 정규화: '### # 1.' -> '### 1.'
    def normalize_header(h):
        return re.sub(r'^(#+)\s*#+\s*', r'\1 ', h).strip()

    for part in sections:
        if not part.strip(): continue
        
        # 헤더 발견 시
        if part.startswith('#'):
            normalized_part = normalize_header(part)
            # 레벨 계산 (### -> 3)
            level_match = re.match(r'^(#+)', normalized_part)
            level = len(level_match.group()) if level_match else 1
            
            # 브레드크럼 갱신 (레벨에 맞춰 하위 스택 조정)
            header_text = normalized_part.lstrip('#').strip()
            
            # 이전 내용 저장 후 초기화 (내용이 있을 경우)
            if current_content.strip():
                breadcrumb_str = " > ".join(current_breadcrumbs)
                chunks.append({
                    "breadcrumb": breadcrumb_str,
                    "text": current_content.strip()
                })
            
            # 레벨에 따라 브레드크럼 스택 조정
            if level == 1:
                current_breadcrumbs = [title, header_text]
            else:
                current_breadcrumbs = current_breadcrumbs[:level]
                while len(current_breadcrumbs) < level:
                    current_breadcrumbs.append("...") # 중간 단계 누락 시 채우기
                if len(current_breadcrumbs) == level:
                    current_breadcrumbs.append(header_text)
                else:
                    current_breadcrumbs[level] = header_text
            
            current_content = normalized_part + "\n"
        else:
            current_content += part
            
    # 마지막 남은 부분 처리
    if current_content.strip():
        breadcrumb_str = " > ".join(current_breadcrumbs)
        chunks.append({
            "breadcrumb": breadcrumb_str,
            "text": current_content.strip()
        })

    # 너무 긴 청크는 재귀적으로 분할 (글자 수 기준)
    final_chunks = []
    seen_sentences = set() # 동일 문서 내 중복 문장 방지 (Sliding Window 대응)
    
    for item in chunks:
        # 본문 알맹이만 추출 (헤더 제외)
        content_lines = item["text"].split("\n")
        body_content = "\n".join([line for line in content_lines if not line.strip().startswith('#')]).strip()
        
        # 알맹이가 너무 짧은(20자 미만) '껍데기 제목 청크'는 버림
        if len(body_content) < 20:
            continue
            
        # 중복 문장 제거 (자연어 특성상 완벽하진 않지만 대략적인 문맥 중복 제거)
        # 30자 이상의 긴 문장이 이전에 등장했다면 해당 청크에서 제거 시도
        filtered_lines = []
        for line in content_lines:
            s_line = line.strip()
            if len(s_line) > 30 and s_line in seen_sentences:
                continue
            if len(s_line) > 30:
                seen_sentences.add(s_line)
            filtered_lines.append(line)
        
        cleaned_text = "\n".join(filtered_lines).strip()
        if len(cleaned_text.replace('#', '').strip()) < 20:
            continue

        if len(cleaned_text) > chunk_size:
            # 보수적으로 문장 단위 분할 시도
            sub_parts = re.split(r'(?<=\. )', cleaned_text)
            temp_sub = ""
            for p in sub_parts:
                if len(temp_sub) + len(p) > chunk_size:
                    final_chunks.append(f"### [위치: {item['breadcrumb']}]\n\n{temp_sub.strip()}")
                    temp_sub = p
                else:
                    temp_sub += p
            if temp_sub:
                final_chunks.append(f"### [위치: {item['breadcrumb']}]\n\n{temp_sub.strip()}")
        else:
            final_chunks.append(f"### [위치: {item['breadcrumb']}]\n\n{cleaned_text}")
            
    return final_chunks

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
        
        # 2. 마크다운 구조 인식형 청킹 수행
        smart_chunks = markdown_aware_chunking(content, title, chunk_size=800, overlap=150)
        
        # 3. 메타데이터 보강 및 저장 (필터링 적용)
        current_doc_chunks = 0
        for i, chunk in enumerate(smart_chunks):
            # 가치 기반 필터링 적용 (헤더 정보를 포함한 상태로 검사)
            if not is_useful_chunk(chunk):
                filtered_count += 1
                continue
                
            chunked_data.append({
                "source": source_name,
                "title": title,
                "chunk_id": current_doc_chunks + 1,
                "content": chunk.strip()
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