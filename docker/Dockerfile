# ──────────────────────────────────────────────
# 엣지 세이버 Dockerfile (재황님 담당)
# ──────────────────────────────────────────────
#
# TODO (재황님):
#   1. Python 베이스 이미지 선택 (경량: python:3.11-slim)
#   2. 필요한 패키지만 설치 (requirements.txt 기반)
#   3. RPi용 ARM 이미지 대응
# ──────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사
COPY . .

# 실행
CMD ["python", "main.py"]
