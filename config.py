import os

# ── 시스템 전역 설정 ──
APP_NAME = "엣지 세이버 (Edge Saver)"
DEBUG = True

# ── LLM & STT 모델 설정 ──
# [v35] Ollama Native 호출을 위한 모델명 (속도와 정확도를 위한 명작 qwen2.5 탑재)
LLM_MODEL = "qwen3.5:0.8b"
STT_ENABLED = False  # [v48] 라즈베리파이 오디오 드라이버(ALSA) 세그멘테이션 오류 방지를 위해 비활성화
STT_ENGINE = "WHISPER"
STT_GEMMA_MODEL = "qwen2.5:1.5b"
STT_WHISPER_MODEL = "large-v3-turbo"
NATIVE_EMBEDDING_MODEL = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"  # FAISS 기반 Native RAG용 임베딩 모델
OLLAMA_BASE_URL = "http://127.0.0.1:11434"  # DNS 조회 지연 방지를 위해 localhost 대신 IP 직접 지정

# ── TTS(음성 출력) 설정 ──
# [v47] Piper 공식 한국어 모델 부재로 인해, 즉각적인 오프라인 반응이 가능한 SAPI5 기반으로 임시 롤백
TTS_ENGINE = "PYTTSX3"
TTS_RATE = 190  # SAPI5(pyttsx3)의 부드러운 표준 속도 (기본 150~200)
PIPER_MODEL = "models/piper/piper-kss-korean.onnx"
PIPER_CONFIG = "models/piper/piper-kss-korean.onnx.json"

# ── RAG 설정 ──
VECTORDB_DIR = "chroma_db"
FAISS_INDEX_DIR = "faiss_db"
DATA_DIR = "data"
CHUNK_SIZE = 250    # [초고속 최적화] 지식 조각당 길이를 절반 이하로 줄여 AI 읽기 시간 50% 단축
CHUNK_OVERLAP = 50

# ── 센서 임계값 설정 ──
SENSOR_THRESHOLDS = {
    "smoke_mq2": 300,
    "gas_mq135": 400,
    "temperature_high": 60,
    "temperature_low": -10,
    "humidity_low": 15,
}

# ── 위험도 Level 기준 ──
RISK_LEVELS = {
    1: "주의",
    2: "경고",
    3: "위험",
    4: "긴급",
    5: "재난",
}

# ── 카메라 설정 ──
CAMERA_INDEX = 0
CAPTURE_WIDTH = 640
CAPTURE_PATH = "temp_capture.jpg"
