import os
import json
import sys

# 프로젝트 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
utils_dir = current_dir
rag_dir = os.path.dirname(utils_dir)
project_root = os.path.dirname(rag_dir)

# rag 폴더를 경로에 추가하여 parser.py를 찾을 수 있게 함
if rag_dir not in sys.path:
    sys.path.append(rag_dir)

# parser.py의 핵심 기능 임포트
try:
    from parser import (
        ManualParser
    )
    # 필요한 메서드들은 ManualParser 인스턴스를 통해 호출하거나 정적으로 가져옴
    parser_inst = ManualParser()
    extract_text_with_pdf = parser_inst.extract_text_with_pdf
    extract_text_with_hwp = parser_inst.extract_text_with_hwp
    clean_noise = parser_inst.clean_noise
    sanitize_content_with_ai = parser_inst.sanitize_content_with_ai
except ImportError as e:
    print(f"[오류] parser.py에서 필요한 기능을 가져올 수 없습니다: {e}")
    sys.exit(1)

# 모든 매뉴얼 파일을 자동으로 복구 대상으로 지정
def get_all_manuals():
    raw_path = os.path.join(project_root, "data", "raw_documents")
    return [f for f in os.listdir(raw_path) if f.endswith(('.pdf', '.hwp', '.txt'))]

TARGET_FILES = get_all_manuals()

def recover():
    print("🚀 [복구 시작] 119 응급처치 매뉴얼 '초정밀 환각 방지 전사' 가동...", flush=True)
    
    # 기존 데이터 로드
    parsed_path = os.path.join(project_root, "data", "parsed_manuals.json")
    with open(parsed_path, "r", encoding="utf-8") as f:
        all_docs = json.load(f)

    # 매뉴얼 데이터를 소스 이름으로 맵핑
    doc_map = {doc["source"]: doc for doc in all_docs}

    for filename in TARGET_FILES:
        file_path = os.path.join(project_root, "data", "raw_documents", filename)
        if not os.path.exists(file_path):
            print(f"  [경고] 파일을 찾을 수 없음: {filename}", flush=True)
            continue

        print(f"  [처리 중] {filename} (진행도를 감시 중입니다...)", flush=True)
        
        # 1. 원본 텍스트 추출
        ext = os.path.splitext(filename)[1].lower()
        raw_text = ""
        if ext == ".pdf":
            raw_text = extract_text_with_pdf(file_path)
        elif ext == ".hwp":
            raw_text = extract_text_with_hwp(file_path)
        elif ext == ".txt":
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    raw_text = f.read()
            except Exception as e:
                print(f"  [오류] 텍스트 파일 읽기 실패: {e}")
            
        if not raw_text:
            print(f"  [실패] {filename} 텍스트 추출 실패", flush=True)
            continue

        # 2. 노이즈 제거
        clean_data = clean_noise(raw_text)
        
        # 3. AI 기반 초정밀 전사 (강화된 환각 방지 프롬프트 적용됨)
        recovery_dir = os.path.join(project_root, "data", "manual_recovery")
        os.makedirs(recovery_dir, exist_ok=True)
        cache_path = os.path.join(recovery_dir, f"{filename}.sanitized.md")
        
        final_content = sanitize_content_with_ai(clean_data, cache_path)

        # 4. 데이터 교체
        doc_map[filename] = {
            "source": filename,
            "content": final_content
        }
        
        # 실시간 저장: 파일 하나 끝날 때마다 상태 기록
        with open(parsed_path, "w", encoding="utf-8") as f:
            json.dump(list(doc_map.values()), f, ensure_ascii=False, indent=4)
            
        print(f"  [완료] {filename} 복원 및 실시간 저장 성공! (경로: {cache_path})", flush=True)
        
    print("\n✅ [복구 완료] 오염된 데이터가 초정밀 전사본으로 교체되었습니다.")
    print("이제 'python rag/chunker.py'를 실행하여 클린 청크를 생성하세요.")

if __name__ == "__main__":
    recover()
