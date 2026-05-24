import os
import json

def clean_junk_data():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    recovery_dir = os.path.join(project_root, "data", "manual_recovery")
    json_path = os.path.join(project_root, "data", "parsed_manuals.json")
    
    blacklist = [
        "제공해주신 텍스트", "내용이 포함되어 있지", "정제할 수 없습니다", 
        "가이드 내용을 제공해 주시기 바랍니다", "텍스트가 없습니다"
    ]
    
    removed_count = 0
    
    print("[정화 작업 시작] 오염된 AI 메타 발언 데이터 제거 중...")
    
    # 1. .sanitized.md 파일 및 청크 파일 청소
    if os.path.exists(recovery_dir):
        for filename in os.listdir(recovery_dir):
            if filename.endswith(".md"):
                file_path = os.path.join(recovery_dir, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    if any(bad in content for bad in blacklist):
                        print(f"  [삭제] 오염 감지: {filename}")
                        os.remove(file_path)
                        removed_count += 1
                except Exception as e:
                    print(f"  [오류] {filename} 읽기 실패: {e}")

    # 2. parsed_manuals.json 정화
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            clean_data = []
            for item in data:
                content = item.get("content", "")
                if not any(bad in content for bad in blacklist) and content.strip():
                    clean_data.append(item)
                else:
                    print(f"  [제거] JSON 항목 삭제: {item.get('source', '알 수 없음')}")
            
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(clean_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"  [오류] JSON 정화 실패: {e}")

    print(f"\n[정화 완료] 총 {removed_count}개의 오염된 파일이 제거되었습니다.")

if __name__ == "__main__":
    import sys
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    clean_junk_data()
