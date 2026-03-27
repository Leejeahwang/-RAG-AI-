import win32com.client as win32
import os
import glob
import json
import re
import fitz  # PyMuPDF
import requests
import sys

# 인코딩 문제 발생 시 강제 종료 방지
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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
        return full_text
    except Exception as e:
        print(f"[{os.path.basename(file_path)}] PDF 오류: {e}")
        return None

# --- 2. 텍스트 정제 함수 ---
def clean_noise(text):
    if not text: return ""
    
    # 허용할 문자 패턴 (한글, 영문, 숫자 및 기본 특수문자)
    safe_pattern = re.compile(r'[^가-힣a-zA-Z0-9\s.,!?()\[\]\-"\':;·•➊-➓▶●■※○-◎◇◈-]')
    text = safe_pattern.sub('', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
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
                },
                timeout=90
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
    return (garbage_len / total_len) > 0.05

# --- 2.5 Ollama 기반 필터링 ---
def is_valuable_manual(text, model="qwen2.5:3b"):
    sample_text = text[:1500]
    prompt = f"""
    다음 텍스트가 매뉴얼/가이드북인지(PASS), 아니면 홍보물/개인정보/단순 공지인지(FILTER) 판별하세요.
    [내용]
    {sample_text}
    [결과 (PASS/FILTER)]
    """
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False
            },
            timeout=30
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
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.XHwpWindows.Item(0).Visible = False 
except Exception as e:
    print("[정보] HWP 애플리케이션을 찾을 수 없습니다. PDF만 처리합니다.")

# 데이터 파일은 data/ 디렉토리, 스크립트는 rag/에 위치
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

file_list = glob.glob(os.path.join(project_root, "data", "raw_documents/*"))
target_files = {}

for file in file_list:
    base_name, ext = os.path.splitext(file)
    ext = ext.lower()
    if ext not in ['.hwp', '.pdf']:
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
        
    if raw_text:
        clean_data = clean_noise(raw_text)
        is_valid, reason = is_valid_manual(clean_data)
        
        if is_valid:
            ai_pass, ai_reason = is_valuable_manual(clean_data)
            
            if ai_pass:
                final_content = clean_data
                if looks_broken(clean_data):
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