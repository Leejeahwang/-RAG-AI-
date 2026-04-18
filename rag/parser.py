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

class ManualParser:
    """
    HWP, PDF, 이미지 파일에서 텍스트를 추출하고 AI를 통해 정제하는 통합 파서 클래스.
    """
    def __init__(self, use_ai_refinement=True, llm_model="gemma4:e2b"):
        self.use_ai_refinement = use_ai_refinement
        self.llm_model = llm_model
        self._ocr_reader = None
        
        # MuPDF 내부 구문 에러 로그가 콘솔을 어지럽히지 않도록 차단
        try:
            fitz.TOOLS.mupdf_display_errors(False)
        except:
            pass

    def get_ocr_reader(self):
        if self._ocr_reader is None:
            print("    [OCR] 모델 초기화 중 (한국어/영어)...")
            self._ocr_reader = easyocr.Reader(['ko', 'en'], gpu=True)
        return self._ocr_reader

    def release_ocr_reader(self):
        if self._ocr_reader is not None:
            print("    [OCR] 리소스 해제 중...")
            del self._ocr_reader
            self._ocr_reader = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    # --- 추출 핵심 로직 (정적 메서드로 유지하여 클래스 없이도 호출 가능하게 함) ---
    @staticmethod
    def extract_text_with_hwp(file_path):
        try:
            f = olefile.OleFileIO(file_path)
            dirs = f.listdir()
            bodytext_sections = [d for d in dirs if d[0] == "BodyText" and "Section" in d[1]]
            bodytext_sections.sort(key=lambda x: int(re.search(r'\d+', x[1]).group()))
            
            full_text = []
            is_compressed = False
            if ["FileHeader"] in dirs:
                header_node = f.openstream("FileHeader")
                header_data = header_node.read()
                if header_data[36] & 1:
                    is_compressed = True
            
            for section_node in bodytext_sections:
                stream = f.openstream(section_node)
                data = stream.read()
                if is_compressed:
                    try: data = zlib.decompress(data, -15)
                    except:
                        try: data = zlib.decompress(data)
                        except: pass
                
                try:
                    decoded = data.decode('utf-16le', errors='ignore')
                    cleaned = re.sub(r'[\x00-\x1f]', '', decoded)
                    cleaned = re.sub(r'[\x7f-\xff]', '', cleaned)
                    full_text.append(cleaned)
                except Exception as e:
                    print(f"      [경고] {section_node} 디코딩 실패: {e}")
            f.close()
            return "\n".join(full_text)
        except Exception as e:
            print(f"[{os.path.basename(file_path)}] HWP 분석 오류: {e}")
            return None

    def extract_text_with_pdf(self, file_path):
        try:
            doc = fitz.open(file_path)
            full_text = []
            for page in doc:
                page_dict = page.get_text("dict")
                lines_data = []
                for b in page_dict["blocks"]:
                    if "lines" in b:
                        for l in b["lines"]:
                            y_pos = (l["bbox"][1] + l["bbox"][3]) / 2
                            current_line_text = []
                            for s in l["spans"]:
                                text = s["text"].strip()
                                if not text: continue
                                if re.search(r'[^\x00-\x7F가-힣\s]{2,}', text) or len(re.findall(r'[?.!@#$%^&*()]', text)) > len(text)*0.3:
                                    text = self.laser_ocr_scan(page, s["bbox"])
                                current_line_text.append(text)
                            if current_line_text:
                                lines_data.append({"y": y_pos, "text": " ".join(current_line_text)})
                
                lines_data.sort(key=lambda x: x["y"])
                merged_page_text = []
                if lines_data:
                    current_row = lines_data[0]["text"]
                    last_y = lines_data[0]["y"]
                    for i in range(1, len(lines_data)):
                        if abs(lines_data[i]["y"] - last_y) < 5:
                            current_row += " " + lines_data[i]["text"]
                        else:
                            merged_page_text.append(current_row)
                            current_row = lines_data[i]["text"]
                            last_y = lines_data[i]["y"]
                    merged_page_text.append(current_row)
                full_text.append("\n".join(merged_page_text))
            doc.close()
            
            final_raw_text = "\n\n--- PAGE BREAK ---\n\n".join(full_text)
            meaningful_chars = re.sub(r'[\s\-]+', '', final_raw_text)
            if len(meaningful_chars) < 50:
                print(f"    [품질 경고] 텍스트 밀도 부족. OCR 전체 스캔 전환...")
                return self.extract_text_with_ocr(file_path)
            return final_raw_text
        except Exception as e:
            print(f"    [PDF 분석 오류] {e}. OCR 스캔으로 대체.")
            return self.extract_text_with_ocr(file_path)

    def extract_text_with_ocr(self, file_path):
        try:
            reader = self.get_ocr_reader()
            full_text = []
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.pdf':
                doc = fitz.open(file_path)
                for page in doc:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    results = reader.readtext(np.array(img), detail=0)
                    full_text.append("\n".join(results))
                doc.close()
            else:
                results = reader.readtext(file_path, detail=0)
                full_text.append("\n".join(results))
            return "\n\n--- PAGE BREAK ---\n\n".join(full_text)
        except Exception as e:
            print(f"    [OCR 오류] {e}")
            return ""

    def laser_ocr_scan(self, page, bbox):
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=bbox)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            reader = self.get_ocr_reader()
            results = reader.readtext(np.array(img), detail=0)
            return " ".join(results) if results else "[판독불가]"
        except: return "[판독불가]"

    @staticmethod
    def clean_noise(text):
        if not text: return ""
        text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        toxic_hallucinations = ['쌀알', '대꽉츄', '뀀엀', '탅', '듈법', '봀SUM', '눀7AJ', '쀄', '녔', '띲', '먚']
        for toxic in toxic_hallucinations:
            text = text.replace(toxic, '[판독불가]')
        
        # [교정] 한글+영문/숫자 혼용 단어를 파괴하던 공격적인 정규식 완화
        # 이제 AI가 정제 과정에서 문맥을 보고 복원하도록 원본을 최대한 유지합니다.
        # text = re.sub(r'\b(?=[^ \n]*[가-힣])(?=[^ \n]*[a-zA-Z0-9])[^ \n]{3,}\b', '[판독불가]', text)
        
        return text.strip()

    def sanitize_content_with_ai(self, text, basename):
        """AI를 사용하여 텍스트의 구조를 복원합니다."""
        if not text: return ""
        print(f"      [지능형 구조 복원] AI 수행 중 ({basename})...")
        prompt = f"""
당신은 재난 안전 가이드 전문 편집자입니다. 아래 텍스트를 RAG에 최적화된 마크다운으로 정제하세요.

### 지침:
1. **정밀 복원**: `[판독불가]` 태그나 오타(예: `솗수점`, `능력단윋`)가 있다면 문맥을 고려하여 원래의 올바른 기술적 용어(예: `소수점`, `능력단위`)로 복원하세요.
2. **구조화 및 무결성**: 표 구조를 복합 리스트나 테이블로 복원하되, **데이터 오정렬(Hallucination)**에 극도로 주의하세요. 수치와 항목의 연결이 불확실하다면 억지로 표에 끼워 넣지 말고 리스트로 나열하세요.
3. **평문 유지 (No LaTeX & No Math Mode)**: 수식 모드(`$`)나 LaTeX 문법(예: `\text{...}`, `\rightarrow`)을 **절대 사용하지 마세요**. 
    - 화학 용어 및 단위: `CO2`, `kg`, `m`, `1.8kg`
    - 화학 반응식: 아래첨자 없이 숫자를 연달아 쓰고, 화살표는 `->`를 사용하세요. (예: `NaHCO3 -> Na2CO3 + CO2 + H2O`)
    - 모든 기술 정보를 인간이 읽기 편한 평문으로만 표기하세요. (단, 원문의 통화 기호 등은 보존합니다.)
4. **지능형 헤더**: 적절한 마크다운 헤더(#, ##)를 부여하세요.

텍스트:
{text}
"""
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self.llm_model, "prompt": prompt, "stream": False},
                timeout=180
            )
            content = response.json().get("response", "").strip()
            
            # [안전 장치] AI가 지침을 어기고 생성한 LaTeX 기호 강제 제거
            # 1. $\text{...}$ 또는 \text{...} 형태 제거
            content = re.sub(r'\$\\text\{(.+?)\}\$', r'\1', content)
            content = re.sub(r'\\text\{(.+?)\}', r'\1', content)
            
            # 2. 화학식 아래첨자(_) 평문화 (예: CO_2 -> CO2)
            content = re.sub(r'_\{(\d+)\}', r'\1', content)
            content = re.sub(r'_(\d+)', r'\1', content)
            
            # 3. 화살표 및 특수 기호 평문화
            content = content.replace('\\rightarrow', '->')
            content = content.replace('\\Rightarrow', '=>')
            
            # 4. 모든 $ 기호 최종 제거 (수식 모드 원천 차단)
            # 단, 원문에 명확한 통화 표시가 있는 경우를 제외하고는 모두 제거
            # (안전 매뉴얼 특성상 수식 모드 오용이 99%이므로 일괄 제거가 안전함)
            content = content.replace('$', '')
            
            return content
        except Exception as e:
            print(f"      [AI 복원 오류] {e}")
            return text

    def is_valuable_manual(self, text, filename):
        """
        문서가 실질적인 '재난 대응 행동 지침'인지 판별합니다.
        단순 행정 지원(보상금, 복구 지원 등)은 필터링합니다.
        """
        # 1. 원천 차단 키워드 (행정/보상 중심)
        administrative_keywords = ['지원안내', '보상금', '복구지원', '행정절차', '신청서', '포상']
        if any(kw in filename for kw in administrative_keywords):
            print(f"    [검역] 행정 키워드 감지됨 ({filename}). AI 정밀 판정 모드 가동.")
        
        # 2. AI 정밀 판정 (주제 분류)
        sample_text = text[:1500]
        prompt = f"""
당신은 재난 안전 전문 가이드 분류기입니다. 아래 문서가 '재난 발생 시 즉각적인 행동 요령(Action Manual)'인지, 아니면 '사후 행정 지원/보상 안내(Administrative Support)'인지 판별하세요.

### 판별 기준:
- **PASS**: 화재, 지진 등 재난 시 대피 방법, 소방시설 조작법, 응급처치 등 '행동 지침'이 포함된 경우.
- **FILTER**: 재난 복구 지원금 신청, 보상 절차, 행정 기구 안내 등 '사후 행정/금전적 지원' 중심인 경우.

### 문서 정보:
- 파일명: {filename}
- 내용 요약: {sample_text}

결과만 출력하세요 (PASS 또는 FILTER):
"""
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self.llm_model, "prompt": prompt, "stream": False},
                timeout=30
            )
            result = response.json().get("response", "").strip().upper()
            is_pass = "PASS" in result
            return is_pass, result
        except Exception as e:
            print(f"    [검역 오류] AI 판정 실패: {e}")
            return True, "SYSTEM_DEFAULT_PASS"

    def parse_file(self, file_path):
        """단일 파일을 파싱하여 결과 딕셔너리를 반환합니다."""
        basename = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        print(f"[처리 중] {basename}")
        
        raw_text = ""
        if ext == '.hwp': raw_text = self.extract_text_with_hwp(file_path)
        elif ext == '.pdf': raw_text = self.extract_text_with_pdf(file_path)
        elif ext in ['.png', '.jpg', '.jpeg']: raw_text = self.extract_text_with_ocr(file_path)
        elif ext == '.txt':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    raw_text = f.read()
            except Exception as e:
                print(f"  [오류] 텍스트 파일 읽기 실패: {e}")
        
        if not raw_text or len(raw_text) < 500:
            print(f"  [건너뜀] 유효하지 않은 내용 (길이 부족 등)")
            return None
            
        clean_data = self.clean_noise(raw_text)
        ai_pass, _ = self.is_valuable_manual(clean_data, basename)
        if not ai_pass:
            print(f"  [건너뜀] 부적절한 내용 필터링됨")
            return None
            
        final_content = clean_data
        if self.use_ai_refinement:
            final_content = self.sanitize_content_with_ai(clean_data, basename)
            
        print(f"  [통과] 수락됨: {len(final_content)} 자")
        return {"source": basename, "content": final_content}

# --- 기존 CLI 호환용 ---
if __name__ == "__main__":
    parser = ManualParser()
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_list = glob.glob(os.path.join(project_root, "data", "raw_documents/*"))
    
    all_documents = []
    for f in file_list:
        res = parser.parse_file(f)
        if res: all_documents.append(res)
    
    parser.release_ocr_reader()
    save_path = os.path.join(project_root, "data", "parsed_manuals.json")
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(all_documents, f, ensure_ascii=False, indent=4)
    print(f"\n[완료] {len(all_documents)}개 문서 저장됨.")