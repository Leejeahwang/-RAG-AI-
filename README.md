# 🚑 엣지 세이버 (Edge Saver)

> 라즈베리파이 5에서 **카메라로 현장을 감지** → **AI가 상황 분석** → **응급처치/대응법을 음성+화면으로 즉시 제공**하는 오프라인 AI 구조 비서

---

## 🚀 프로젝트 소개

이 프로젝트는 인터넷 연결이 불안정한 재난 상황에서도 작동하는 **오프라인 AI 비서**입니다. 적십자 응급처치 매뉴얼을 데이터베이스화하여, 카메라 영상 분석과 음성 질문을 통해 가장 정확하고 안전한 정보를 실시간으로 제공합니다.

**핵심 기능:**
- **Vision AI:** 카메라로 현장 상황을 실시간 분석 (OpenCV + LLaVA)
- **Local RAG:** 신뢰할 수 있는 매뉴얼 데이터 기반 답변 생성 (환각 방지)
- **오프라인 음성:** STT/TTS로 음성 질문 인식 및 답변 읽어주기
- **한국어 특화 LLM:** Qwen 2.5 (1.5B) 모델 활용

---

## 🛠️ 설치 및 실행 방법

### 1. 필수 프로그램 설치

1. **Python 3.11 이상** — [다운로드](https://www.python.org/downloads/)
2. **Ollama** (로컬 LLM 엔진) — [다운로드](https://ollama.com)

### 2. 패키지 설치

```bash
pip install langchain langchain-community langchain-core langchain-classic langchain-text-splitters chromadb
```

### 3. AI 모델 다운로드

```bash
ollama pull qwen2.5:1.5b
```

### 4. 실행

```bash
# 기본 실행 (Vision AI 시뮬레이션)
python main.py

# 특정 사진을 넘겨 실행할 경우
python main.py 테스트사진.png
```

---

## 📂 프로젝트 구조

```text
-RAG-AI-/
├── config.py                    # 전역 설정 (모델명, 경로, 파라미터)
├── main.py                      # E2E 통합 진입점 (Vision 연동 등)
│
├── rag/                         # RAG 모듈 (승훈, 종화)
│   ├── loader.py                #   문서 로딩 & 청킹 (승훈)
│   ├── retriever.py             #   벡터DB 생성 & 검색 (승훈)
│   ├── chain.py                 #   QA 체인 & 프롬프트 (승훈)
│   └── pdf_parser.py            #   PDF 파싱 (종화)
│
├── vision/                      # Vision 모듈 (규태)
│   └── camera.py                #   카메라 캡처 (구현 예정)
│
├── voice/                       # Voice 모듈 (종화)
│   ├── stt.py                   #   오프라인 음성 인식 (vosk)
│   └── tts.py                   #   오프라인 음성 합성 (pyttsx3)
│
├── gui/                         # GUI 모듈 (승훈)
│   └── app.py                   #   터치스크린 GUI (구현 예정)
│
├── docker/                      # Docker 설정 (재황)
│   ├── docker-compose.yml       #   멀티 서비스 구성
│   └── Dockerfile               #   컨테이너 빌드
│
├── edge_saver_manual.txt        # 응급처치 매뉴얼 데이터
├── PROJECT_STATUS.md            # 구현 현황 & 담당자
├── implementation_plan.md       # 개발 로드맵 & 역할분담
├── .gitignore
└── README.md
```

---

## 👥 팀원

| 이름 | 역할 | 담당 모듈 |
|------|------|-----------|
| 이재황 | PM & DevOps | `docker/`, 라즈베리파이 환경 |
| 박규태 | Vision AI | `vision/` |
| 이승훈 | RAG Search & GUI | `rag/`, `gui/` |
| 채종화 | Voice & PDF Data | `voice/`, `rag/pdf_parser.py` |
