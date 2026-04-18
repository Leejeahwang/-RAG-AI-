import json
import os
import sys

# UTF-8 출력 보장 (Windows 호환)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def generate_preview():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    input_file = os.path.join(project_root, "data", "chunked_manuals.json")
    output_file = os.path.join(project_root, "data", "preview_chunks.md")

    if not os.path.exists(input_file):
        print(f"[오류] {input_file} 파일이 없습니다.")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# 📂 RAG 데이터 청크 미리보기 (최신 무결성 버전)\n\n")
        f.write("> [!IMPORTANT]\n")
        f.write("> **본 파일은 AI 메타 발언이 제거되고 안전 수칙이 100% 복구된 최신 데이터셋을 반영합니다.**\n\n")
        
        current_source = ""
        for i, chunk in enumerate(chunks):
            if current_source != chunk["source"]:
                current_source = chunk["source"]
                f.write(f"\n--- \n## 📄 출처: {current_source}\n")
            
            chunk_id = chunk.get("chunk_id", i + 1)
            f.write(f"\n### [청크 ID: {chunk_id}] (출처: {chunk['source']})\n")
            f.write(f"{chunk['content']}\n")
            f.write("\n---\n")

    print(f"[정보] {output_file} 업데이트 완료! ({len(chunks)}개 청크 반영)")

if __name__ == "__main__":
    generate_preview()
