# 🚑 엣지 세이버(Edge Saver) - 지능형 재난 안전 RAG 시스템

이 프로젝트는 통신망이 단절된 극한의 재난 상황에서도 '국민재난안전포털'의 풍부한 가이드라인을 바탕으로, 사용자에게 즉각적이고 정확한 행동 요령을 제공하는 **오프라인 특화형 RAG(Retrieval-Augmented Generation) AI 비서**입니다.

---

## 🏗️ 시스템 구성 (Core Modules)

프로젝트는 핵심 기능을 담당하는 3개의 모듈로 구성되어 있습니다.

### 1. 전처리 파이프라인 (`rag/`)
재난 안전 데이터를 수집하고 AI가 읽기 쉬운 형태로 가공합니다.
- **`crawler.py`**: 재난안전포털의 최신 매뉴얼을 자동으로 수집합니다.
- **`parsing.py`**: HWP/PDF 문서에서 텍스트를 추출하고 AI 필터링을 거쳐 정제합니다.
- **`chunking.py`**: 추출된 텍스트를 검색에 최적화된 크기(청크)로 분할합니다.

### 2. 가공 데이터 저장소 (`data/`)
- **`raw_documents/`**: 수집된 원본 매뉴얼 파일들이 저장됩니다.
- **`parsed_manuals.json`**: 추출 및 정제된 매뉴얼 데이터입니다.
- **`chunked_manuals.json`**: 검색용 벡터 DB 구축에 사용되는 최종 데이터입니다.

### 3. 지능형 음성 인터페이스 (`voice/`)
- **`stt.py`**: `faster-whisper` 기반의 고성능 오프라인 음성 인식 모듈입니다.
- **`tts.py`**: AI의 답변을 자연스러운 한국어 음성으로 출력하는 모듈입니다.

---

## 🚀 실행 방법 (Quick Start)

### 1. 환경 설정
- **Python 3.11+** 및 **Ollama**가 설치되어 있어야 합니다.
- 필요한 모델 다운로드: `ollama pull qwen2.5:1.5b`

### 2. 라이브러리 설치
```bash
pip install langchain langchain-community chromadb requests selenium webdriver-manager PyMuPDF pywin32 numpy pyaudio faster-whisper pyttsx3
```

### 3. 시스템 가동
프로젝트 루트에서 아래 명령어를 실행하여 AI 비서와 대화를 시작합니다.
```bash
python main.py
```

---

## 📂 프로젝트 구조
```text
RAG_Data&voice/
├── data/               # 매뉴얼 및 가공 데이터
├── rag/                # 전처리 파이프라인 (crawler, parsing, chunking)
├── voice/              # 음성 인터페이스 (stt, tts)
├── main.py             # [핵심] 프로젝트 통합 실행 파일
└── README.md           # [현재 파일] 프로젝트 안내서
```
