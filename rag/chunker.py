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
            },
            timeout=60
        )
        ai_title = response.json().get("response", "").strip()
        # 불필요한 따옴표나 마크다운 기호 제거
        ai_title = re.sub(r'["\'#\.\(\)]', '', ai_title)
        return ai_title if ai_title else filename
    except Exception as e:
        print(f"  [오류] AI 타이틀 추출 실패 ({filename}): {e}")
        return filename

# --- 1.5 AI 기반 문맥 분할 지점 식별 (Semantic Splitting) ---
def get_semantic_splits(text, model="qwen3.5:4b"):
    """
    AI를 사용하여 텍스트 내에서 문맥이 전환되는 지점을 식별하고 [SPLIT] 마커를 삽입합니다.
    """
    if len(text) < 400: # 너무 짧으면 굳이 AI를 쓰지 않음
        return text

    prompt = f"""
당신은 재난 안전 가이드 편집자입니다. 아래 텍스트에서 주제가 바뀌거나 다른 유형의 행동 요령이 시작되는 지점을 찾아내어 '[SPLIT]' 마커를 삽입하세요.

### 규칙:
1. 단순히 문장이 끝난다고 나누지 마세요. 전체적인 **주제나 카테고리(예: 예방법 -> 행동요령 -> 사후지도)**가 바뀌는 핵심 지점에만 '[SPLIT]'을 넣으세요.
2. 관련 있는 행동 지침들은 하나의 덩어리로 유지하여 문맥을 보존하세요.
3. 각 덩어리가 약 400~600자 내외가 되도록 흐름을 조절하세요.
4. 텍스트를 수정하거나 요약하지 말고, 원본 텍스트 사이에 '[SPLIT]' 마커만 삽입하세요.

### 원본 텍스트:
{text}
"""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=90
        )
        final_result = response.json().get("response", "").strip()
        
        # --- [추가] AI 거절 멘트 검역 (Safety Guard) ---
        blacklist = [
            "제공해주신 텍스트", "내용이 포함되어 있지", "정제할 수 없습니다", 
            "가이드 내용을 제공해 주시기 바랍니다", "텍스트가 없습니다"
        ]
        if any(bad in final_result for bad in blacklist):
            return "" # 빈 문자열 반환 (나중에 폐기됨)
            
        return final_result
    except Exception:
        return text

# --- 2. 마크다운 구조 인식형 스마트 분할기 (Structural + Semantic Chunking) ---
def markdown_aware_chunking(text, title, chunk_size=600, overlap=100):
    """
    마크다운 헤더와 AI 문맥 분석을 결합하여 지능적으로 분할합니다.
    """
    # 1. 헤더 기준으로 대분류
    sections = re.split(r'(^#{1,4} .+)', text, flags=re.MULTILINE)
    
    pre_chunks = []
    current_breadcrumbs = [title]
    current_content = ""
    
    def normalize_header(h):
        return re.sub(r'^(#+)\s*#+\s*', r'\1 ', h).strip()

    for part in sections:
        if not part.strip(): continue
        if part.startswith('#'):
            normalized_part = normalize_header(part)
            level = len(re.match(r'^(#+)', normalized_part).group())
            header_text = normalized_part.lstrip('#').strip()
            
            if current_content.strip():
                pre_chunks.append({"breadcrumb": " > ".join(current_breadcrumbs), "text": current_content.strip()})
            
            if level == 1: current_breadcrumbs = [title, header_text]
            else:
                current_breadcrumbs = current_breadcrumbs[:level]
                while len(current_breadcrumbs) < level: current_breadcrumbs.append("...")
                if len(current_breadcrumbs) == level: current_breadcrumbs.append(header_text)
                else: current_breadcrumbs[level] = header_text
            current_content = normalized_part + "\n"
        else:
            current_content += part
            
    if current_content.strip():
        pre_chunks.append({"breadcrumb": " > ".join(current_breadcrumbs), "text": current_content.strip()})

    # 2. 대분류된 섹션 내에서 AI 시맨틱 분할 수행
    final_chunks = []
    for item in pre_chunks:
        # 본문 알맹이 추출
        lines = item["text"].split("\n")
        header = lines[0] if lines[0].startswith('#') else ""
        body = "\n".join(lines[1:]) if header else item["text"]
        
        if len(body) > chunk_size * 0.8:
            print(f"    [AI 시맨틱 분할] {item['breadcrumb']} 처리 중...")
            semantic_text = get_semantic_splits(body)
            # AI가 삽입한 [SPLIT] 마커 기준으로 쪼갬
            sub_parts = semantic_text.split("[SPLIT]")
        else:
            sub_parts = [body]

        # 3. 물리적 상한선(Safety Guard) 적용
        for p in sub_parts:
            p = p.strip()
            if not p or len(p) < 20: continue
            
            # 여전히 너무 길면 강제 분할 (단, 표 구조(|)가 중간에 있으면 자르지 않음)
            if len(p) > chunk_size and "|" not in p:
                force_parts = re.split(r'(\n\n|\. )', p)
                tmp = ""
                for fp in force_parts:
                    if len(tmp) + len(fp) > chunk_size:
                        final_chunks.append(f"### [위치: {item['breadcrumb']}]\n\n{header}\n{tmp.strip()}".strip())
                        tmp = fp
                    else:
                        tmp += fp
                if tmp:
                    final_chunks.append(f"### [위치: {item['breadcrumb']}]\n\n{header}\n{tmp.strip()}".strip())
            else:
                # 표가 포함되어 있거나 길이가 적절하면 그대로 추가
                final_chunks.append(f"### [위치: {item['breadcrumb']}]\n\n{header}\n{p.strip()}".strip())
            
    return final_chunks

# --- 2.5 가치 중심 청크 필터링 ---
def is_useful_chunk(text):
    """
    RAG 지식으로서 가치가 낮은 청크(메타데이터, 단순연락처 등)를 필터링합니다.
    """
    # 1. 길이 검사 (너무 짧으면 무의미)
    if len(text.strip()) < 60:
        return False
        
    # 2. 특수문자 비중 검사 (보수적 적용: 안전 수칙은 불렛포인트가 많음)
    total_len = len(text)
    alnum_len = len(re.findall(r'[가-힣a-zA-Z0-9]', text))
    if total_len > 0 and (alnum_len / total_len) < 0.4:
        return False
        
    # 3. 금지 키워드 검사 (발행처, 저작권, 연락처 정보 등)
    noise_keywords = [
        '발행처', '발행일', '발행인', '내용감수', '편집디자인', 
        '저작권', '무단 전재', '전화번호', '팩스번호', '이메일',
        'TEL', 'FAX', 'E-mail', '주소 : ', '홈페이지'
    ]
    
    match_count = 0
    for kw in noise_keywords:
        if kw in text:
            match_count += 1
    if match_count >= 2:
        return False
        
    # 4. 외계어(Garbage Hangul) 검사
    # 현대 한국어 문서에서 거의 쓰이지 않는 깨진 글자들(뀀, 엀, 탅 등)이 많은지 확인
    suspicious_chars = re.findall(r'[가-힣]', text)
    if suspicious_chars:
        garbage_pattern = r'[뀀엀탅탂랮랭킴씀좻업엉곀엇퉧업퉱뒴뒇뒇듇뒼곓럂톳쀄겳쐀얭탇귗짌쀀겼퀀츀봀났탆냀킻찀럃듈듈]'
        garbage_matches = re.findall(garbage_pattern, text)
        if len(garbage_matches) / len(suspicious_chars) > 0.05: # 외계어 비중 5% 초과 시 제거
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