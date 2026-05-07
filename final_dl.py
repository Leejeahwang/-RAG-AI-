import requests
import os

# 브라우저인 것처럼 속이는 헤더 (이게 없으면 15바이트 에러가 납니다)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def download_verified(url, path):
    print(f"{path} 다운로드 시도 중...", end=" ", flush=True)
    r = requests.get(url, headers=headers, allow_redirects=True, stream=True)
    if r.status_code == 200:
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"성공! ({os.path.getsize(path)} bytes)")
    else:
        print(f"실패 (에러코드: {r.status_code})")

os.makedirs("models/piper", exist_ok=True)
base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ko/ko_KR/kyutae/medium/"

download_verified(base_url + "ko_KR-kyutae-medium.onnx", "models/piper/ko_KR-kyutae-medium.onnx")
download_verified(base_url + "ko_KR-kyutae-medium.onnx.json", "models/piper/ko_KR-kyutae-medium.onnx.json")
