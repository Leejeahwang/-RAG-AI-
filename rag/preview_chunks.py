import json
import os

def create_markdown_preview():
    # 경로 설정
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    input_file = os.path.join(project_root, "data", "chunked_manuals.json")
    output_file = os.path.join(project_root, "data", "preview_chunks.md")

    print(f"[정보] '{input_file}'를 마크다운 미리보기 파일로 변환 중...")

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)
    except FileNotFoundError:
        print(f"[오류] '{input_file}' 파일이 없습니다. chunker.py를 먼저 실행하세요.")
        return

    # 마크다운 내용 작성
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# 📑 RAG 청크 마크다운 미리보기\n")
        f.write(f"이 파일은 AI가 실제로 검색하게 될 **{len(chunks)}개**의 청크를 시각화한 파일입니다.\n\n")
        f.write("---\n\n")

        for i, chunk in enumerate(chunks):
            f.write(f"### [청크 ID: {chunk['chunk_id']}] (출처: {chunk['source']})\n")
            f.write(chunk['content'])
            f.write("\n\n---\n\n")

    print(f"[성공] '{output_file}' 파일이 생성되었습니다. 이제 VS Code에서 마크다운 미리보기로 확인하세요!")

if __name__ == "__main__":
    create_markdown_preview()
