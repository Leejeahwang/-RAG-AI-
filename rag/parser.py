import os
import glob
import json
import re
import fitz  # PyMuPDF
import requests
import sys
import easyocr
import numpy as np
import io
import gc
import torch
import olefile  # HWP 패키지 분석용
import zlib     # HWP 압축 해제용
from PIL import Image

# 인코딩 문제 발생 시 강제 종료 방지
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
 
# --- 설정 옵션 ---
USE_AI_REFINEMENT = True  # AI 기반 구조화 활성화 (Markdown 형식 출력)
LLM_MODEL_FOR_CLEANING = "gemma4:e2b" # 보다 강력한 고도화 성능을 위해 gemma4 사용

# --- 0. OCR 설정 ---
# GPU가 있으면 사용, 없으면 CPU (약 1GB 모델 다운로드 발생)
_ocr_reader = None

def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        print("    [OCR] 모델 초기화 중 (한국어/영어)...")
        _ocr_reader = easyocr.Reader(['ko', 'en'], gpu=True) # gpu=True는 있으면 자동 사용
    return _ocr_reader

def release_ocr_reader():
    """OCR 리소스를 해제하여 GPU/RAM 메모리를 LLM이나 다른 공정에 반환합니다."""
    global _ocr_reader
    if _ocr_reader is not None:
        print("    [OCR] 리소스 해제 중...")
        del _ocr_reader
        _ocr_reader = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

# --- 1. 텍스트 추출 함수 ---
def extract_text_with_hwp(file_path):
    """
    한컴오피스를 실행하지 않고 olefile로 HWP 내부 바이너리를 직접 읽어서 텍스트를 추출합니다.
    보안 팝업이 절대로 뜨지 않으며 속도가 매우 빠릅니다.
    """
    try:
        f = olefile.OleFileIO(file_path)
        dirs = f.listdir()
        
        # HWP v5 이상은 BodyText 스토리지에 Section0, Section1 ... 에 내용이 저장됨
        bodytext_sections = [d for d in dirs if d[0] == "BodyText" and "Section" in d[1]]
        # 인덱스 순서대로 정렬 (Section0, Section1 ...)
        bodytext_sections.sort(key=lambda x: int(re.search(r'\d+', x[1]).group()))
        
        full_text = []
        
        # 문서 정보(압축 여부 등) 확인
        is_compressed = False
        if ["FileHeader"] in dirs:
            header_node = f.openstream("FileHeader")
            header_data = header_node.read()
            # FileHeader의 36번째 바이트가 압축 여부 (0x01: compressed)
            if header_data[36] & 1:
                is_compressed = True
        
        for section_node in bodytext_sections:
            stream = f.openstream(section_node)
            data = stream.read()
            
            # 압축 해제 (Deflate 방식)
            if is_compressed:
                try:
                    data = zlib.decompress(data, -15)
                except Exception:
                    # 일부 버전은 표준 zlib 헤더를 가질 수도 있음
                    try:
                        data = zlib.decompress(data)
                    except:
                        pass
            
            # UTF-16LE 인코딩으로 변환 (HWP 기본 텍스트 인코딩)
            try:
                decoded = data.decode('utf-16le', errors='ignore')
                # 바이너리 값인 태그들 제거 (HWP 제어 문자들)
                cleaned = re.sub(r'[\x00-\x1f]', ' ', decoded)
                full_text.append(cleaned)
            except Exception as e:
                print(f"      [경고] {section_node} 디코딩 실패: {e}")
        
        f.close()
        return "\n".join(full_text)
    
    except Exception as e:
        print(f"[{os.path.basename(file_path)}] HWP 분석 오류: {e}")
        return None

def extract_text_with_pdf(file_path):
    try:
        doc = fitz.open(file_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()
        
        # 텍스트가 너무 적거나 형식이 깨진 경우 이미지 기반 PDF로 간주하고 OCR 시도
        if len(full_text.strip()) < 100:
            print(f"    [알림] '{os.path.basename(file_path)}'에서 디지털 텍스트가 부족하거나 형식이 깨졌습니다. OCR을 시도합니다.")
            return extract_text_with_ocr(file_path)
            
        return full_text
    except Exception as e:
        print(f"    [PDF 오류] '{os.path.basename(file_path)}' 분석 실패: {e}. OCR로 전환합니다.")
        return extract_text_with_ocr(file_path)

def extract_text_with_ocr(file_path):
    try:
        reader = get_ocr_reader()
        ext = os.path.splitext(file_path)[1].lower()
        full_text = []

        if ext == '.pdf':
            doc = fitz.open(file_path)
            print(f"    [OCR] PDF {len(doc)}페이지 변환 및 분석 중...")
            for i, page in enumerate(doc):
                # 고해상도 이미지 변환 (300 DPI)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("png")
                
                # EasyOCR은 numpy array 또는 파일 경로를 받음
                img = Image.open(io.BytesIO(img_data))
                img_np = np.array(img)
                
                results = reader.readtext(img_np, detail=0)
                page_text = " ".join(results)
                full_text.append(page_text)
                print(f"      - {i+1}페이지 완료")
            doc.close()
        else:
            # 일반 이미지 파일 (.png, .jpg 등)
            results = reader.readtext(file_path, detail=0)
            full_text.append(" ".join(results))
            
        return "\n\n".join(full_text)
    except Exception as e:
        print(f"    [OCR 오류] {e}")
        return None

# --- 2. 텍스트 정제 함수 ---
def clean_noise(text):
    if not text: return ""
    
    # 1. 제어 문자 및 비가시 문자 완벽 제거 (Whitelist 방식)
    # 한글, 영문, 숫자, 공백, 주요 문장 부호(\n 포함)만 남김
    safe_pattern = re.compile(r'[^가-힣a-zA-Z0-9\s.,!?()\[\]\-"\':;·•➊-➓▶●■※○-◎◇◈\n\-_]')
    text = safe_pattern.sub('', text)
    
    # 2. 비정상적인 공백 조합 정규화 (예: "화 재" -> "화재")
    # 두 글자 사이의 단일 공백이 한글인 경우 결합 시도 (heuristic)
    text = re.sub(r'([가-힣])\s([가-힣])', r'\1\2', text)
    # 한 번 더 실행하여 3글자 이상도 처리
    text = re.sub(r'([가-힣])\s([가-힣])', r'\1\2', text)

    # 3. 문서 레이아웃 기호 및 반복 문자 제거 (. . . , ---, ━━━ 등)
    text = re.sub(r'\.{2,}', ' ', text)
    text = re.sub(r'·{2,}', ' ', text)
    text = re.sub(r'-{3,}', ' ', text)
    text = re.sub(r'={3,}', ' ', text)
    text = re.sub(r'[━─|｜│]{1,}', ' ', text)
    
    # 4. 페이지 번호 단독 행 제거 (예: "\n 12 \n")
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
    
    # 5. 불필요한 줄바꿈 정리
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

# --- 2.2 AI 기반 텍스트 최적화 ---
def sanitize_content_with_ai(text, filename, model=LLM_MODEL_FOR_CLEANING):
    if not text: return ""
    
    # 너무 짧은 텍스트는 정제하지 않음
    if len(text) < 100: return text

    # 텍스트를 적절한 크기로 분할하여 AI 정제 (Sliding Window 적용으로 문맥 보존)
    window_size = 4000
    overlap = 500
    text_chunks = []
    for i in range(0, len(text), window_size - overlap):
        text_chunks.append(text[i:i + window_size])
        if i + window_size >= len(text):
            break
    
    processed_text = []

    print(f"    [AI 매뉴얼 고도화] {len(text_chunks)}개 블록 처리 중... (파일: {filename})")
    
    for idx, chunk in enumerate(text_chunks):
        prompt = f"""
        당신은 '초정밀 텍스트 전사 전문가'입니다. 아래 제공된 [데이터]를 글자 하나 빠짐없이 마크다운으로 옮기세요.
        
        [절대 규칙]
        1. 100% 무조건 전사: 모든 안전 수칙, 대응 절차, 수치, 단어 하나도 생략하거나 요약하지 마세요. 
        2. 자의적 판단 금지: 데이터가 혼재되어 보이거나 손상되어 보여도 절대 '재구성'하거나 '정리'하지 마세요. 있는 그대로만 출력하세요.
        3. 변명 금지: "제공해주신 데이터는...", "내용이 손상되어..."와 같은 모든 AI의 메타 코멘트를 '절대' 입력하지 마세요.
        4. 순수 본문만 출력: 서론, 결론, 인사말 없이 오직 마크다운으로 변환된 본문만 출력하세요. 만약 데이터가 정말 비어있다면 공백만 반환하세요.
        5. 가독성: OCR 오류로 흩어진 글자가 있다면 문맥에 맞게 한글 단어로만 결합하세요.

        [데이터]
        {chunk}
        """
        
        success = False
        for retry in range(3): # 최대 3번 재시도
            try:
                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "top_p": 0.9,
                            "num_predict": 4096,
                            "stop": ["---", "제공하신", "원본 데이터"]
                        }
                    },
                    timeout=180 # 3분 타임아웃
                )
                cleaned = response.json().get("response", "").strip()
                
                if cleaned and len(cleaned) > (len(chunk) * 0.2):
                    processed_text.append(cleaned)
                    success = True
                    break
                else:
                    print(f"      [경고] {idx+1}번 블록 결과 미흡, 재시도 중... ({retry+1}/3)")
            except Exception as e:
                print(f"      [경고] {idx+1}번 블록 타임아웃/오류, 재시도 중... ({retry+1}/3): {e}")
        
        if not success:
            print(f"      [실패] {idx+1}번 블록 최종 실패. 원본 데이터를 유지합니다.")
            processed_text.append(chunk)

    return "\n\n".join(processed_text)

def looks_broken(text):
    if not text: return False
    total_len = len(text)
    garbage_len = len(re.findall(r'[^가-힣a-zA-Z0-9\s.,!?()\[\]\-"\':;]', text))
    return (garbage_len / total_len) > 0.3  # 5% -> 30%로 완화

# --- 2.5 Ollama 기반 필터링 ---
def is_valuable_manual(text, filename, model=LLM_MODEL_FOR_CLEANING):
    # --- [건너뜀 방지 1] 파일명 기반 키워드 검사 ---
    safe_keywords = ['매뉴얼', '요령', '가이드', '지침', '안전', '수칙', '대비']
    if any(kw in filename for kw in safe_keywords):
        return True, "FILENAME_KEYWORD_PASS"

    sample_text = text[:1500]
    # --- [건너뜀 방지 2] 프롬프트 개선: 표지/저작권 정보 언급 ---
    prompt = f"""
    당신은 재난 안전 전문 가이드 분류기입니다. 아래 텍스트가 실질적인 '매뉴얼/가이드북'인지 판별하세요.
    주의: 문서의 앞부분에는 발행처 정보, 저작권, 연락처 등 '표지 정보'가 포함될 수 있으며 이는 정상적인 매뉴얼의 일부입니다.
    텍스트의 제목이나 맥락이 안전 수칙이나 행동 지침을 담고 있다면 PASS를 출력하세요.
    단순한 '홍보 포스터', '개인정보 이용약관', 또는 '단순 공지사항'인 경우에만 FILTER를 출력하세요.

    [파일명]
    {filename}
    [내용 (문서 앞부분)]
    {sample_text}

    결과만 출력하세요 (PASS 또는 FILTER):
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
        result = response.json().get("response", "").strip().upper()
        return "PASS" in result, result
    except Exception as e:
        print(f"  [오류] Ollama 필터링 실패: {e}")
        return True, "SYSTEM_DEFAULT_PASS"

def is_valid_manual(text):
    if len(text) < 500:
        return False, "내용 너무 짧음 (<500자)"
    return True, "유효한 길이"

# --- 3. 파서 실행 ---
print("[정보] 문서 파서 초기화 중...")

# 데이터 파일은 data/ 디렉토리, 스크립트는 rag/에 위치
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

file_list = glob.glob(os.path.join(project_root, "data", "raw_documents/*"))
target_files = {}

for file in file_list:
    base_name, ext = os.path.splitext(file)
    ext = ext.lower()
    if ext not in ['.hwp', '.pdf', '.png', '.jpg', '.jpeg']:
        continue
    
    if base_name not in target_files:
        target_files[base_name] = []
    target_files[base_name].append(ext)

# 우선순위: HWP > PDF
final_targets = []
for base_name, exts in target_files.items():
    if '.hwp' in exts:
        final_targets.append(base_name + '.hwp')
    elif '.pdf' in exts:
        final_targets.append(base_name + '.pdf')

print(f"[정보] {len(file_list)}개 파일 발견. {len(final_targets)}개의 고유 대상 처리 중.\n")

all_documents = []

for file in final_targets:
    basename = os.path.basename(file)
    print(f"[처리 중] {basename}")
    
    ext = os.path.splitext(file)[1].lower()
    raw_text = ""
    
    if ext == '.hwp':
        raw_text = extract_text_with_hwp(file)
    elif ext == '.pdf':
        raw_text = extract_text_with_pdf(file)
    elif ext in ['.png', '.jpg', '.jpeg']:
        raw_text = extract_text_with_ocr(file)
        
    if raw_text:
        clean_data = clean_noise(raw_text)
        is_valid, reason = is_valid_manual(clean_data)
        
        if is_valid:
            # 파일명을 함께 전달하여 키워드 기반 필터링 우회 적용
            ai_pass, ai_reason = is_valuable_manual(clean_data, basename)
            
            if ai_pass:
                final_content = clean_data
                # AI 마크다운 정제 실행
                if USE_AI_REFINEMENT:
                    final_content = sanitize_content_with_ai(clean_data, basename)
                
                all_documents.append({
                    "source": basename,
                    "content": final_content
                })
                print(f"  [통과] 수락됨: {len(final_content)} 자")
            else:
                print(f"  [건너뜀] 부적절한 내용으로 필터링됨")
        else:
            print(f"  [건너뜀] {reason}")
    else:
        print("  [건너뜀] 텍스트 추출 실패")

# 작업 종료
release_ocr_reader()

save_path = os.path.join(project_root, "data", "parsed_manuals.json")
with open(save_path, 'w', encoding='utf-8') as f:
    json.dump(all_documents, f, ensure_ascii=False, indent=4)

print(f"\n[정보] 파서 종료. {len(all_documents)}개의 매뉴얼이 '{save_path}'에 저장되었습니다.")