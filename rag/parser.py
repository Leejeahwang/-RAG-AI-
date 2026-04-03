import win32com.client as win32
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
from PIL import Image

# 인코딩 문제 발생 시 강제 종료 방지
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
 
# --- 설정 옵션 ---
USE_AI_REFINEMENT = False  # 속도 향상을 위해 기본적으로 끔 (필곡 활성화 시 True로 변경)

# --- 0. OCR 설정 ---
# GPU가 있으면 사용, 없으면 CPU (약 1GB 모델 다운로드 발생)
_ocr_reader = None

def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        print("    [OCR] 모델 초기화 중 (한국어/영어)...")
        _ocr_reader = easyocr.Reader(['ko', 'en'], gpu=True) # gpu=True는 있으면 자동 사용
    return _ocr_reader

# --- 1. 텍스트 추출 함수 ---
def extract_text_with_hwp(file_path, hwp_app):
    try:
        abs_path = os.path.abspath(file_path)
        hwp_app.Open(abs_path, "HWP", "forceopen:true")
        hwp_app.InitScan()
        
        full_text = ""
        while True:
            state, text = hwp_app.GetText()
            if state in [0, 1]: 
                break
            full_text += text
            
        hwp_app.ReleaseScan()
        return full_text
    
    except Exception as e:
        print(f"[{os.path.basename(file_path)}] HWP 오류: {e}")
        return None

def extract_text_with_pdf(file_path):
    try:
        doc = fitz.open(file_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        
        # 텍스트가 너무 적으면 이미지 기반 PDF로 간주하고 OCR 시도
        if len(full_text.strip()) < 100:
            print(f"    [알림] '{os.path.basename(file_path)}'에서 디지털 텍스트가 부족합니다. OCR을 시도합니다.")
            return extract_text_with_ocr(file_path)
            
        return full_text
    except Exception as e:
        print(f"[{os.path.basename(file_path)}] PDF 오류: {e}")
        return None

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
    
    # 1. 문서 레이아웃 기호 및 반복 문자 제거 (. . . , ---, ━━━ 등)
    text = re.sub(r'\.{2,}', ' ', text)  # 연속된 점 제거
    text = re.sub(r'·{2,}', ' ', text)  # 연속된 가운뎃점 제거
    text = re.sub(r'-{3,}', ' ', text)  # 연속된 하이픈 제거
    text = re.sub(r'={3,}', ' ', text)  # 연속된 등호 제거
    text = re.sub(r'[━─]{2,}', ' ', text) # 연속된 선 기호 제거
    
    # 2. 허용할 문자 패턴 (한글, 영문, 숫자 및 기본 특수문자) - 노이즈 제거
    safe_pattern = re.compile(r'[^가-힣a-zA-Z0-9\s.,!?()\[\]\-"\':;·•➊-➓▶●■※○-◎◇◈-]')
    text = safe_pattern.sub('', text)
    
    # 3. 불필요한 제어 문자 및 HTML 태그 제거
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    
    # 4. 페이지 번호 단독 행 제거 (예: "\n 12 \n")
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
    
    # 5. 공백 정규화
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

# --- 2.2 AI 기반 텍스트 최적화 ---
def sanitize_content_with_ai(text, model="qwen2.5:3b"):
    if not text: return ""
    
    chunk_size = 1500
    text_chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    processed_text = []

    print(f"    [AI 정제] {len(text_chunks)}개 블록 처리 중...")
    
    for idx, chunk in enumerate(text_chunks):
        prompt = f"""
        당신은 매뉴얼 전문 편집자입니다. HWP/PDF에서 추출된 다음 텍스트의 레이아웃을 깔끔하게 정리해 주세요.
        기술적인 세부 사항은 100% 동일하게 유지하면서 공백과 줄바꿈만 정규화하십시오.
        [블록 {idx+1}/{len(text_chunks)}]
        {chunk}
        [결과]
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
            cleaned = response.json().get("response", "").strip()
            if cleaned:
                processed_text.append(cleaned)
            else:
                processed_text.append(chunk) 
        except Exception as e:
            print(f"      [오류] 블록 {idx+1} 실패: {e}")
            processed_text.append(chunk)

    return "\n\n".join(processed_text)

def looks_broken(text):
    if not text: return False
    total_len = len(text)
    garbage_len = len(re.findall(r'[^가-힣a-zA-Z0-9\s.,!?()\[\]\-"\':;]', text))
    return (garbage_len / total_len) > 0.3  # 5% -> 30%로 완화

# --- 2.5 Ollama 기반 필터링 ---
def is_valuable_manual(text, filename, model="qwen2.5:3b"):
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

hwp = None
try:
    # 캐시를 정리했으므로 가장 안정적인 EnsureDispatch 방식으로 원복합니다.
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.XHwpWindows.Item(0).Visible = False 
except Exception as e:
    print(f"[정보] HWP 애플리케이션 연결 실패 (에러 내용: {e})")
    print("[정보] PDF 및 이미지 파일만 처리합니다.")

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
    
    if ext == '.hwp' and hwp:
        raw_text = extract_text_with_hwp(file, hwp)
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
                # AI 정제 사용 여부 및 노이즈 기준 확인
                if USE_AI_REFINEMENT and looks_broken(clean_data):
                    print(f"  [AI 정제] 높은 노이즈 레벨 감지. 텍스트 재구조화 중...")
                    final_content = sanitize_content_with_ai(clean_data)
                
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

if hwp:
    hwp.Quit()

save_path = os.path.join(project_root, "data", "parsed_manuals.json")
with open(save_path, 'w', encoding='utf-8') as f:
    json.dump(all_documents, f, ensure_ascii=False, indent=4)

print(f"\n[정보] 파서 종료. {len(all_documents)}개의 매뉴얼이 '{save_path}'에 저장되었습니다.")