import os
import json
import sys

# 프로젝트 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(current_dir)

# parser.py의 핵심 기능 임포트
try:
    from parser import (
        extract_text_with_pdf, 
        extract_text_with_hwp, 
        clean_noise, 
        sanitize_content_with_ai
    )
except ImportError:
    print("[오류] parser.py에서 필요한 함수를 가져올 수 없습니다.")
    sys.exit(1)

# 복구 대상 리스트 (우선순위 1순위 전용)
TARGET_FILES = [
    "180911_화재 국민행동 매뉴얼.pdf"
]

def recover():
    print("🚀 [복구 시작] 오염된 핵심 매뉴얼 4종 초정밀 재파싱 진행 중...")
    
    # 기존 데이터 로드
    parsed_path = os.path.join(project_root, "data", "parsed_manuals.json")
    with open(parsed_path, "r", encoding="utf-8") as f:
        all_docs = json.load(f)

    # 매뉴얼 데이터를 소스 이름으로 맵핑
    doc_map = {doc["source"]: doc for doc in all_docs}

    for filename in TARGET_FILES:
        file_path = os.path.join(project_root, "data", "raw_documents", filename)
        if not os.path.exists(file_path):
            print(f"  [경고] 파일을 찾을 수 없음: {filename}")
            continue

        print(f"  [처리 중] {filename} (초정밀 전사 중...)")
        
        # 1. 원본 텍스트 추출
        ext = os.path.splitext(filename)[1].lower()
        raw_text = ""
        if ext == ".pdf":
            raw_text = extract_text_with_pdf(file_path)
        elif ext == ".hwp":
            raw_text = extract_text_with_hwp(file_path)
            
        if not raw_text:
            print(f"  [실패] {filename} 텍스트 추출 실패")
            continue

        # 2. 노이즈 제거
        clean_data = clean_noise(raw_text)
        
        # 3. AI 기반 초정밀 전사 (이미 parser.py의 프롬프트가 강화된 상태)
        # 100% 전사 모드 적용
        final_content = sanitize_content_with_ai(clean_data, filename)

        # 4. 데이터 교체
        doc_map[filename] = {
            "source": filename,
            "content": final_content
        }
        print(f"  [완료] {filename} 복원 성공 ({len(final_content)} 자)")

    # 최종 결과 저장
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(list(doc_map.values()), f, ensure_ascii=False, indent=4)
        
    print("\n✅ [복구 완료] 오염된 데이터가 초정밀 전사본으로 교체되었습니다.")
    print("이제 'python rag/chunker.py'를 실행하여 클린 청크를 생성하세요.")

if __name__ == "__main__":
    recover()
