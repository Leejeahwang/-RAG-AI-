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
                # HWP 제어 문자 및 불필요한 바이너리 태그 제거 보강
                cleaned = re.sub(r'[\x00-\x1f]', '', decoded) # 제어문자 제거
                cleaned = re.sub(r'[\x7f-\xff]', '', cleaned) # 확장 아스키 노이즈 제거
                full_text.append(cleaned)
            except Exception as e:
                print(f"      [경고] {section_node} 디코딩 실패: {e}")
        
        f.close()
        return "\n".join(full_text)
    
    except Exception as e:
        print(f"[{os.path.basename(file_path)}] HWP 분석 오류: {e}")
        return None

def extract_text_with_pdf(file_path):
    """
    좌표 기반 정밀 전사 엔진: 글자의 X, Y 위치를 분석하여 표 구조를 복원하고,
    손상된 영역(판독불가)만 고해상도 OCR로 타겟 스캔합니다.
    """
    try:
        doc = fitz.open(file_path)
        full_text = []
        
        for page in doc:
            # 1. 좌표 기반 데이터 획득
            page_dict = page.get_text("dict")
            lines_data = []
            
            for b in page_dict["blocks"]:
                if "lines" in b:
                    for l in b["lines"]:
                        # 라인의 Y좌표(중심값)를 기준으로 그룹화하기 위해 저장
                        y_pos = (l["bbox"][1] + l["bbox"][3]) / 2
                        current_line_text = []
                        for s in l["spans"]:
                            text = s["text"].strip()
                            if not text: continue
                            
                            # [판독불가] 의심 구간 탐지: 특수문자가 너무 많거나 깨진 패턴
                            if re.search(r'[^\x00-\x7F가-힣\s]{2,}', text) or len(re.findall(r'[?.!@#$%^&*()]', text)) > len(text)*0.3:
                                # 해당 구역만 고해상도 레이저 OCR 가동
                                bbox = s["bbox"]
                                text = laser_ocr_scan(page, bbox)
                            
                            current_line_text.append(text)
                        
                        if current_line_text:
                            lines_data.append({"y": y_pos, "text": " ".join(current_line_text)})
            
            # 2. Y좌표 순으로 정렬 후 같은 행(오차 3pt 이내)끼리 병합
            lines_data.sort(key=lambda x: x["y"])
            merged_page_text = []
            if lines_data:
                current_row = lines_data[0]["text"]
                last_y = lines_data[0]["y"]
                
                for i in range(1, len(lines_data)):
                    if abs(lines_data[i]["y"] - last_y) < 5: # 5pt로 상향하여 병합율 극대화
                        current_row += " " + lines_data[i]["text"]
                    else:
                        merged_page_text.append(current_row)
                        current_row = lines_data[i]["text"]
                        last_y = lines_data[i]["y"]
                merged_page_text.append(current_row)
            
            full_text.append("\n".join(merged_page_text))
            
        doc.close()
        
        # --- [추가] 텍스트 밀도 자가 진단 ---
        final_raw_text = "\n\n--- PAGE BREAK ---\n\n".join(full_text)
        # 유의미한 글자수 체크 (공백, 기호 제외)
        meaningful_chars = re.sub(r'[\s\-]+', '', final_raw_text)
        
        if len(meaningful_chars) < 50:
            print(f"    [품질 경고] 텍스트 밀도 부족({len(meaningful_chars)}자). OCR 강제 모드 전환...")
            return extract_text_with_ocr(file_path)
            
        return final_raw_text
        
    except Exception as e:
        print(f"    [PDF 정밀분석 오류] {e}. OCR 전체 스캔으로 전환합니다.")
        return extract_text_with_ocr(file_path)

def extract_text_with_ocr(file_path):
    """PDF 또는 이미지를 전체 페이지 OCR 스캔하여 텍스트를 추출합니다."""
    try:
        reader = get_ocr_reader()
        full_text = []
        
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            doc = fitz.open(file_path)
            for page in doc:
                # 고해상도로 렌더링 (300 DPI 수준)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                results = reader.readtext(np.array(img), detail=0)
                full_text.append("\n".join(results))
            doc.close()
        else:
            # 단일 이미지 파일
            results = reader.readtext(file_path, detail=0)
            full_text.append("\n".join(results))
            
        return "\n\n--- PAGE BREAK ---\n\n".join(full_text)
    except Exception as e:
        print(f"    [전체 OCR 오류] {e}")
        return ""

def laser_ocr_scan(page, bbox):
    """지정된 영역(bbox)만 고해상도로 도려내어 OCR을 수행합니다."""
    try:
        # 3배율(약 216 DPI 이상) 고해상도 렌더링
        matrix = fitz.Matrix(3, 3)
        pix = page.get_pixmap(matrix=matrix, clip=bbox)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        reader = get_ocr_reader()
        results = reader.readtext(np.array(img), detail=0)
        return " ".join(results) if results else "[판독불가]"
    except:
        return "[판독불가]"

# --- 2. 텍스트 정제 함수 ---
def clean_noise(text):
    if not text: return ""
    
    # 1. 제어 문자 및 비가시 문자 완벽 제거 (Whitelist 방식)
    # 4. 페이지 번호 단독 행 제거 보강
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
    
    # 5. 불필요한 줄바꿈 및 다중 공백 정리
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 6. 알려진 환각 단어 및 외계어 블랙리스트 제거 (강력 소독)
    toxic_hallucinations = [
        '쌀알', '대꽉츄', '뀀엀', '탅', '듈법', '봀SUM', '눀7AJ', '쀄', '녔', '띲', '먚',
        '닀', '곽', '쳎', '뙠', '뺣', '푙', '삦', '삪', '껃', '묀', '끨', '슏', '뼀', '푟',
        '삷', '삩', '꽛', '솭', '붹', '얹', '뒬', '뷅', '탊', '뷆', '듊', '겼', '쎔', '찄', '푴'
    ]
    for toxic in toxic_hallucinations:
        text = text.replace(toxic, '[판독불가]')
    
    # 7. 기괴한 한글 조합 (쌀+외계어, 닀+외계어 등) 정규식 소독
    # '쌀'로 시작하면서 비정상적인 받침이 붙은 경우나 단독 외계어 파편들
    text = re.sub(r'쌀[가-힣]+', '[판독불가]', text)
    text = re.sub(r'[가-힣]*[닀곽쳎뙠뺣푙삦삪껃묀끨슏뼀푟삷삩꽛솭붹얹뒬뷅탊뷆듊겼쎔찄푴][가-힣]*', '[판독불가]', text)
    
    # 8. 비정상적인 조합 (한글+영문+숫자 혼재된 깨진 바이너리 패턴) 추가 소독
    # 예: Pt닀B, HmB1B1 등 (길이가 3자 이상이면서 한글과 영숫자가 섞인 경우)
    noise_pattern = re.compile(r'\b(?=[^ \n]*[가-힣])(?=[^ \n]*[a-zA-Z0-9])[^ \n]{3,}\b')
    text = noise_pattern.sub('[판독불가]', text)
    
    return text.strip()

# --- 2.2 AI 기반 텍스트 최적화 ---
def sanitize_content_with_ai(text, cache_path, model="gemma4:e2b"):
    """
    AI를 사용하여 텍스트의 구조를 복원합니다. 
    사용자 요청사항 반영: 표 내부 줄바꿈 '한줄'로 병합, 마크다운 헤더 부여.
    """
    if not text: return ""
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read()

    print(f"      [지능형 구조 복원] AI가 표 재조립 및 제목 부여 중...")
    
    # 속도를 위해 4,000자씩 청크로 나누어 처리 (컨텍스트 유지를 위해 페이지 단위 권장)
    prompt = f"""
당신은 재난 안전 가이드 전문 편집자입니다. 아래 텍스트를 RAG 시스템에 최적화된 마크다운 형식으로 정제하세요.

### 지침:
1. **표 구조 복원**: 계단식으로 뭉개진 표 데이터를 논리적인 '마크다운 테이블' 또는 '불렛 리스트'로 재구성하세요.
2. **한 줄 밀착**: 표의 한 칸(셀) 안에서 여러 줄로 나뉜 텍스트는 반드시 **하나의 문장**으로 병합하세요.
3. **지능형 헤더**: 문서의 파트 구분(예: 구분, 상황, 유형, 행동요령 등)에 마크다운 헤더(#, ##)를 부여하세요.
4. **불필요한 노이즈 제거**: [판독불가] 단어는 문맥상 유추가 가능하면 수정하고, 불가능하면 삭제하세요.
5. **밀도 최적화**: 불필요한 빈 줄을 최소화하여 정보 밀도를 높이세요.

### 텍스트:
{text}
"""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False
            },
            timeout=180
        )
        final_result = response.json().get("response", "").strip()
        
        # --- [추가] AI 거절 멘트 검역 (Safety Guard) ---
        blacklist = [
            "제공해주신 텍스트", "내용이 포함되어 있지", "정제할 수 없습니다", 
            "가이드 내용을 제공해 주시기 바랍니다", "텍스트가 없습니다"
        ]
        if any(bad in final_result for bad in blacklist):
            print(f"      [검역 통과 실패] AI가 내용을 찾지 못함. 해당 구간 폐기.")
            return "" # 빈 문자열 반환 (나중에 청킹 단계에서 자연스럽게 제외됨)

        # 최종 결과 저장
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(final_result)
        return final_result
        
    except Exception as e:
        print(f"      [AI 복원 오류] {e}. 정규식 결과로 대체합니다.")
        return text.strip()

def is_valuable_manual(text, filename, model=LLM_MODEL_FOR_CLEANING):
    safe_keywords = ['매뉴얼', '요령', '가이드', '지침', '안전', '수칙', '대비']
    if any(kw in filename for kw in safe_keywords):
        return True, "FILENAME_KEYWORD_PASS"

    sample_text = text[:1500]
    prompt = f"""
    당신은 재난 안전 전문 가이드 분류기입니다. 아래 텍스트가 실질적인 '매뉴얼/가이드북'인지 판별하세요.
    결과만 출력하세요 (PASS 또는 FILTER):
    [파일명]: {filename}
    [내용]: {sample_text}
    """
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False}
        )
        result = response.json().get("response", "").strip().upper()
        return "PASS" in result, result
    except Exception:
        return True, "SYSTEM_DEFAULT_PASS"

def is_valid_manual(text):
    if len(text) < 500:
        return False, "내용 너무 짧음 (<500자)"
    return True, "유효한 길이"

# --- 3. 파서 실행부 (메인 실행 시에만 가동) ---
if __name__ == "__main__":
    print("[정보] 문서 파서 초기화 중...")

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
                ai_pass, ai_reason = is_valuable_manual(clean_data, basename)
                if ai_pass:
                    final_content = clean_data
                    if USE_AI_REFINEMENT:
                        final_content = sanitize_content_with_ai(clean_data, basename)
                    all_documents.append({"source": basename, "content": final_content})
                    print(f"  [통과] 수락됨: {len(final_content)} 자")
                else:
                    print(f"  [건너뜀] 부적절한 내용으로 필터링됨")
            else:
                print(f"  [건너뜀] {reason}")
        else:
            print("  [건너뜀] 텍스트 추출 실패")

    release_ocr_reader()
    save_path = os.path.join(project_root, "data", "parsed_manuals.json")
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(all_documents, f, ensure_ascii=False, indent=4)
    print(f"\n[정보] 파서 종료. {len(all_documents)}개의 매뉴얼이 '{save_path}'에 저장되었습니다.")