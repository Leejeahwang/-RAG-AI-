"""
🔥 엣지 세이버 (Edge Saver) — 전역 설정

화재 감시 시스템의 모든 설정값을 한 곳에서 관리합니다.
모델을 바꾸거나 센서 임계값을 조정할 때 이 파일만 수정하면 됩니다.
"""

# ── LLM 모델 설정 ──
LLM_MODEL = "batiai/gemma4-e2b:q4"
EMBEDDING_MODEL = "bge-m3"

# ── STT(음성 인식) 설정 ──
STT_ENGINE = "WHISPER"                       # "GEMMA" (통합 모달) 또는 "WHISPER" (전용)
STT_GEMMA_MODEL = "batiai/gemma4-e2b:q4"             # STT용 멀티모달 모델
STT_WHISPER_MODEL = "large-v3"                 # Whisper 모델 (안정성 및 정확도 종결)

# ── RAG 설정 ──
VECTORDB_DIR = "chroma_db"
DATA_DIR = "data"                          # 매뉴얼 데이터 폴더
CHUNK_SIZE = 600                           # 청킹 크기 (자) - 표 데이터 보존을 위해 상향
CHUNK_OVERLAP = 100                         # 청크 오버랩

# ── 센서 임계값 설정 ──
SENSOR_THRESHOLDS = {
    "smoke_mq2": 300,           # MQ-2 연기감지 아날로그 값 기준
    "gas_mq135": 400,           # MQ-135 가스감지 아날로그 값 기준
    "temperature_high": 60,     # 이상 고온 (°C)
    "temperature_low": -10,     # 이상 저온 (°C)
    "humidity_low": 15,         # 이상 저습도 (%)
}

# ── 위험도 Level 기준 ──
# Level 1(주의) ~ Level 5(재난)
RISK_LEVELS = {
    1: "주의",   # 단일 센서 미세 반응
    2: "경고",   # 단일 센서 임계값 초과
    3: "위험",   # 복수 센서 반응 + 카메라 연기 확인
    4: "긴급",   # 복수 센서 + 카메라 불꽃 확인
    5: "재난",   # 다수 구역 동시 반응
}

# ── 카메라 설정 ──
CAMERA_INDEX = 0                           # 카메라 장치 인덱스 (0 = 기본)
CAPTURE_WIDTH = 640                        # 캡처 이미지 최대 너비 (px)
CAPTURE_PATH = "temp_capture.jpg"          # 임시 캡처 저장 경로

# ── 알림 설정 ──
ALERT_BUZZER_PIN = 18                      # GPIO 핀 번호 (부저)
ALERT_LED_PIN = 23                         # GPIO 핀 번호 (경고 LED)
