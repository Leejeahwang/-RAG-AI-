import requests
import os

def download_file(url, path):
    print(f"{path} 다운로드 중...", end=" ", flush=True)
    try:
        r = requests.get(url, allow_redirects=True, stream=True)
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        size = os.path.getsize(path)
        print(f"완료 ({size} bytes)")
    except Exception as e:
        print(f"실패: {e}")

# 폴더 생성
os.makedirs("models/piper", exist_ok=True)

# 다운로드
onnx = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ko/ko_KR/kyutae/medium/ko_KR-kyutae-medium.onnx"
json_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ko/ko_KR/kyutae/medium/ko_KR-kyutae-medium.onnx.json"

download_file(onnx, "models/piper/ko_KR-kyutae-medium.onnx")
download_file(json_url, "models/piper/ko_KR-kyutae-medium.onnx.json")

# config.py 자동 수정
config_path = "config.py"
if os.path.exists(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("piper-kss-korean.onnx", "ko_KR-kyutae-medium.onnx")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("config.py 수정 완료!")
