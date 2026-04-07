import json
import os
import re

def clean_file(file_path):
    if not os.path.exists(file_path):
        return False
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # AI 메타 발언 패턴 (서론, 결론, 자기소개 등)
    patterns = [
        r"제공해주신 원본 데이터는.*?재구성했습니다\.",
        r"문서 정제 및 데이터 구조화 전문가로서.*?",
        r"RAG 시스템이 가장 효과적으로.*?재구성했습니다\.",
        r"본 데이터는.*?재구성한 결과입니다\.",
        r"이 구조화된 데이터는 RAG 시스템이.*?최적화되어 있습니다\.",
        r"이 데이터는 응급 상황에서의.*?유지되어야 합니다\.",
        r"검층 및 영상 진단.*?최적화하겠습니다\.",
        r"---+\s*$", # 파일 끝의 구분선 제거
        r"^---+\s*", # 파일 시작의 구분선 제거
        r"\[정제된 최종 마크다운 결과물\]",
        r"\[RAG 최적화 요약\]"
    ]
    
    cleaned_count = 0
    for item in data:
        original = item["content"]
        new_content = original
        for p in patterns:
            new_content = re.sub(p, "", new_content, flags=re.DOTALL | re.MULTILINE)
        
        # 불필요한 공백 및 중복 줄바꿈 정리
        new_content = re.sub(r'\n{3,}', '\n\n', new_content).strip()
        
        if original != new_content:
            item["content"] = new_content
            cleaned_count += 1
            
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    print(f"  [{os.path.basename(file_path)}] {cleaned_count}개의 항목에서 AI 메타 발언 삭제 완료.")
    return True

def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    files = [
        os.path.join(project_root, "data", "parsed_manuals.json"),
        os.path.join(project_root, "data", "chunked_manuals.json")
    ]
    
    print("[정보] 데이터 내 AI 불필요 발언(Meta-talk) 청소 시작...")
    for f in files:
        clean_file(f)
    print("[정보] 청소 완료.")

if __name__ == "__main__":
    main()
