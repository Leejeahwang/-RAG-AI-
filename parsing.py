import win32com.client as win32
import os
import glob
import json
import re
import fitz  # PyMuPDF
import requests

# --- 1. 텍스트 추출 함수들 ---
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
        print(f"[{os.path.basename(file_path)}] HWP 에러: {e}")
        return None

def extract_text_with_pdf(file_path):
    try:
        doc = fitz.open(file_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        return full_text
    except Exception as e:
        print(f"[{os.path.basename(file_path)}] PDF 에러: {e}")
        return None

# --- 2. 노이즈 제거 및 구조 필터링 함수 ---
def clean_noise(text):
    if not text: return ""
    # <그림 설명> 등 불필요 태그 흔적 날리기
    text = re.sub(r'<[^>]+>', '', text)
    
    # 지저분한 띄어쓰기를 정리하되, 줄바꿈은 최대 2개까지만 문맥 구분을 위해 보존
    text = re.sub(r'[ \t]+', ' ', text)  # 여러 개의 공백/탭을 한 칸 공백으로
    text = re.sub(r'\n{3,}', '\n\n', text) # 3개 이상의 줄바꿈은 2개로 압축
    return text.strip()

# --- 2.5 Ollama 기반 문서 필터링 ---
def is_valuable_manual(text, model="qwen2.5:3b"):
    """
    AI(Ollama)에게 이 문서가 단순 홍보/지역 정보인지 여부를 물어봅니다.
    """
    # 문서가 너무 길면 앞부분 1500자 정도만 보고 판단
    sample_text = text[:1500]
    
    prompt = f"""
다음은 매뉴얼 문서의 일부입니다. 이 내용이 '구체적인 절차나 지식을 담은 정보성 매뉴얼'인지, 아니면 '단순 홍보, 행사 공고, 지역 배달 정보, 광고'인지 판단해주세요.

[문서 내용 시작]
{sample_text}
[문서 내용 끝]

매뉴얼/정보성 문서라면 'PASS'라고만 답변하고, 
홍보/광고/지역정보/정보가 부실한 문서라면 'FILTER'라고만 답변하세요.
답변은 반드시 한 단어(PASS 또는 FILTER)여야 합니다.
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
        
        if "PASS" in result:
            return True, "정보성 문서 (AI PASS)"
        else:
            return False, "불필요 데이터 (AI FILTER)"
            
    except Exception as e:
        print(f"  [Error] Ollama 필터링 중 에러 발생 (기본값 PASS): {e}")
        return True, "에러로 인한 기본 통과"

def is_valid_manual(text):
    # 포스터나 팸플릿은 이미지 위주라 추출되는 텍스트가 극히 적음 (500자 이하 기준 컷)
    if len(text) < 500:
        return False, "텍스트 길이 500자 미만 (포스터/팸플릿 의심)"
    
    # 텍스트가 충분히 길다면 매뉴얼로 합격
    return True, "유효한 매뉴얼"

# --- 3. 본격적인 실행 파트 ---
print("Parser를 가동합니다. HWP와 PDF 처리를 준비합니다...")

# 한글 프로세스는 무거우므로 한 번만 띄워서 계속 재사용
hwp = None
try:
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.XHwpWindows.Item(0).Visible = False # 한글 창 숨기기
except Exception as e:
    print("한글 프로그램 실행 에러 (HWP가 설치되어 있지 않으면 PDF만 진행됩니다):", e)

# 중복 제거 및 우선순위(HWP > PDF) 결정을 위한 파일 그룹핑
file_list = glob.glob("raw_documents/*")
target_files = {}

for file in file_list:
    base_name, ext = os.path.splitext(file)
    ext = ext.lower()
    if ext not in ['.hwp', '.pdf']:
        continue
    
    if base_name not in target_files:
        target_files[base_name] = []
    target_files[base_name].append(ext)

# HWP를 우선으로 최종 타겟 리스트 생성
final_targets = []
for base_name, exts in target_files.items():
    if '.hwp' in exts:
        final_targets.append(base_name + '.hwp')
    elif '.pdf' in exts:
        final_targets.append(base_name + '.pdf')

print(f"✅ 수집된 {len(file_list)}개의 파일 중, 중복 배제 적용하여 총 {len(final_targets)}개의 파싱 대상을 추려냈습니다!\n")

all_documents = []

for file in final_targets:
    print(f"작업 중... : {os.path.basename(file)}")
    
    ext = os.path.splitext(file)[1].lower()
    raw_text = ""
    
    # 확장자에 따른 함수 렌더링 분기
    if ext == '.hwp' and hwp:
        raw_text = extract_text_with_hwp(file, hwp)
    elif ext == '.pdf':
        raw_text = extract_text_with_pdf(file)
        
    if raw_text:
        # 노이즈를 닦아낸 진또배기 텍스트 만들기
        clean_data = clean_noise(raw_text)
        is_valid, reason = is_valid_manual(clean_data)
        
        if is_valid:
            # AI를 통한 2차 검증 (필터링)
            print(f"  AI가 문서 내용을 검토 중...")
            ai_pass, ai_reason = is_valuable_manual(clean_data)
            
            if ai_pass:
                all_documents.append({
                    "source": os.path.basename(file),
                    "content": clean_data
                })
                print(f"  👉 [최종 통과] {ai_reason} ({len(clean_data)}자)")
            else:
                print(f"  ⏩ [패스] {ai_reason}")
        else:
            print(f"  ⏩ [패스] {reason} ({len(clean_data)}자)")
    else:
        print("  ⏩ [패스] 텍스트가 없거나 실패함")

# 한글 프로그램 안전 종료
if hwp:
    hwp.Quit()

# --- 4. 최종 결과물 저장 ---
save_path = "parsed_manuals.json"
with open(save_path, 'w', encoding='utf-8') as f:
    json.dump(all_documents, f, ensure_ascii=False, indent=4)

print(f"\n🎉 완료! 총 {len(all_documents)}개의 진짜배기 매뉴얼 텍스트가 '{save_path}'로 깔끔하게 저장되었습니다!")