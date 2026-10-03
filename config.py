import os

from dotenv import load_dotenv

load_dotenv()

# ── 시스템 전역 설정 ──
APP_NAME = "엣지 세이버 (Edge Saver)"
DEBUG = True
SIMPLE_UI = False  # 라즈베리파이/VNC 터미널 환경 최적화로 툴바 UI 사용 가능 (False 시 툴바 활성화)


# ── LLM & STT 모델 설정 ──
# [v35] Ollama Native 호출을 위한 모델명 (라즈베리파이 0.5B 초가속 적용)
LLM_MODEL = "qwen2.5:0.5b"  # 최종 대응 지침 생성용 초경량 가속 모델 (0.5B)
USE_LLM = True  # True: 0.5B 모델로 답변 생성, False: Reranker 검색 청크를 원본 그대로 즉시 출력 (Zero-LLM RAG)
KEYWORD_MODEL = "qwen2.5:1.5b"  # 시맨틱 쿼리 키워드 고속 추출용 똑똑한 모델 (1.5B)
import platform
STT_ENABLED = (platform.system() == "Windows")  # [v48] 라즈베리파이 오디오 드라이버(ALSA) 세그멘테이션 오류 방지를 위해 RPi는 비활성화, 윈도우는 기본 활성화
STT_ENGINE = "WHISPER"
STT_GEMMA_MODEL = "qwen2.5:0.5b"
STT_WHISPER_MODEL = "large-v3-turbo"
NATIVE_EMBEDDING_MODEL = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"  # FAISS 기반 Native RAG용 임베딩 모델
OLLAMA_BASE_URL = "http://127.0.0.1:11434"  # DNS 조회 지연 방지를 위해 localhost 대신 IP 직접 지정
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").lower()  # auto | gemini | local
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_CONNECT_TIMEOUT = float(os.getenv("GEMINI_CONNECT_TIMEOUT", "2"))
GEMINI_READ_TIMEOUT = float(os.getenv("GEMINI_READ_TIMEOUT", "8"))
GEMINI_RETRY_COOLDOWN = float(os.getenv("GEMINI_RETRY_COOLDOWN", "60"))
GEMINI_SEND_LAYOUT = os.getenv("GEMINI_SEND_LAYOUT", "false").lower() == "true"
OLLAMA_EMERGENCY_TIMEOUT = float(os.getenv("OLLAMA_EMERGENCY_TIMEOUT", "15"))

# ── TTS(음성 출력) 설정 ──
# 옵션:
#  - "PPASO": 초경량 21MB 한국어 온디바이스 엔진 (ONNXRuntime, 빠른 반응과 또렷한 딕션, 권장)
#  - "PYTTSX3": 즉각적인 오프라인 반응 (SAPI5/espeak 기반, 초경량 기본음)
#  - "MELO": 고품질 딥러닝 음성 (MeloTTS 기반, 고성능 가속기 권장)
TTS_ENGINE = "PPASO"
TTS_RATE = 190  # SAPI5(pyttsx3)의 부드러운 표준 속도 (기본 150~200)
TTS_SPEED_SCALING = False  # 위험 단계별 배속(1.2x~1.3x) 활성화 여부 (False: 1.0x 표준 속도 고정)
PPASO_MODEL_DIR = "models/ppaso"
PIPER_MODEL = "models/piper/piper-kss-korean.onnx"
PIPER_CONFIG = "models/piper/piper-kss-korean.onnx.json"

# ── RAG 설정 ──
VECTORDB_DIR = "chroma_db"
FAISS_INDEX_DIR = "faiss_db"
DATA_DIR = "data"
CHUNK_SIZE = 250    # [초고속 최적화] 지식 조각당 길이를 절반 이하로 줄여 AI 읽기 시간 50% 단축
CHUNK_OVERLAP = 50

# ── Reranker 설정 ──
USE_RERANKER = True
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"
RAG_TOP_K = 2  # 0.5B 초소형 모델의 컨텍스트 병목과 인지 부하를 줄이기 위해 상위 청크 반환 개수를 2개로 제한



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

# ── 사이렌 경보 설정 ──
SIREN_MIN_DURATION = 10.0   # 사이렌 최소 유지 시간 (초)
SIREN_FILE_PATH = "data/siren.mp3"       # 사용할 커스텀 사이렌 파일 경로 (비어있으면 기본 주파수 합성음 사용)
SIREN_VOLUME = 0.25        # 사이렌 볼륨 크기 (0.0 ~ 1.0)

