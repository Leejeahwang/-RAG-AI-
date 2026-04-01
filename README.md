# 🚑 엣지 세이버(Edge Saver) - 지능형 재난 안전 RAG 시스템

이 프로젝트는 통신망이 단절된 극한의 재난 상황에서도 '국민재난안전포털'과 '한국소방안전원(KFSI)'의 풍부한 가이드라인을 바탕으로, 사용자에게 즉각적이고 정확한 행동 요령을 제공하는 **오프라인 특화형 RAG(Retrieval-Augmented Generation) AI 비서**입니다.

---

## 🏗️ 시스템 구성 (Core Modules)

프로젝트는 데이터 수집부터 음성 인터페이스까지 3개의 핵심 계층으로 구성되어 있습니다.

### 1. 전처리 파이프라인 (`rag/`)
재난 안전 데이터를 수집하고 AI 검색에 최적화된 형태로 가공합니다.
- **`crawler.py`**: 국민재난안전포털 및 한국소방안전원(KFSI)의 최신 매뉴얼을 자동으로 수집합니다.
- **`parser.py`**: HWP/PDF/이미지 문서에서 텍스트를 추출합니다. 디지털 텍스트가 없는 이미지 기반 문서는 **EasyOCR**을 통해 자동으로 인식합니다. (초고속 정규식 세척 포함)
- **`chunker.py`**: 추출된 텍스트를 의미 있는 단위로 분할합니다. AI 기반 제목 추출 및 가치가 낮은 노이즈(발행처 정보 등) 자동 필터링 기능이 포함되어 있습니다.

### 2. 가공 데이터 저장소 (`data/`)
- **`raw_documents/`**: 수집된 원본 매뉴얼 파일들이 저장됩니다.
- **`parsed_manuals.json`**: 1차로 정제 및 추출된 매뉴얼 데이터입니다.
- **`chunked_manuals.json`**: RAG 검색용 벡터 DB 구축에 사용되는 최종 청크 데이터입니다.

### 3. 지능형 음성 인터페이스 (`voice/`)
- **`stt.py`**: `faster-whisper` 기반의 고성능 오프라인 음성 인식 모듈입니다.
- **`tts.py`**: AI의 답변을 자연스러운 한국어 음성으로 출력하는 모듈입니다.

---

## 🚀 주요 특징 (Key Features)

- **멀티 소스 크롤링**: 정부 포털과 유관 기관(소방청 등)의 데이터를 통합 수집.
- **이미지 기반 문서 OCR**: 텍스트 레이어가 없는 이미지 PDF도 자동으로 글자를 인식하여 지식화.
- **2단계 데이터 정제**: 
    1. `parser`에서 정규식 기반 초고속 노이즈 제거.
    2. `chunker`에서 RAG 답변 품질을 저하시키는 불필요한 메타데이터(발행인, 연락처 등) 자동 필터링.
- **저지연 최적화**: 로컬 LLM(Ollama) 호출을 최소화하고 꼭 필요한 경우에만 정제 과정을 거치도록 설계.

---

## 💻 실행 방법 (Quick Start)

### 1. 환경 설정
- **Python 3.11+** 및 **Ollama** 자가 실행 환경이 필요합니다.
- 모델 다운로드: `ollama pull qwen2.5:1.5b` (또는 권장: `3b`)

### 2. 필수 라이브러리 설치
```bash
pip install langchain langchain-community chromadb requests selenium webdriver-manager PyMuPDF pywin32 numpy pyaudio faster-whisper pyttsx3 easyocr opencv-python-headless
```

### 3. 파이프라인 가동 (데이터 업데이트 시)
```bash
python rag/crawler.py  # 데이터 수집 (선택)
python rag/parser.py   # 텍스트 추출 및 1차 정합
python rag/chunker.py  # 데이터 분할 및 노이즈 필터링
```

### 4. 시스템 실행 (통합 실행)
```bash
python main_test.py
```

---

## 📂 프로젝트 구조
```text
RAG_Data&voice/
├── data/               # 매뉴얼 및 가공 데이터 (.json)
├── rag/                # 전처리 파이프라인 (crawler, parser, chunker)
├── voice/              # 음성 인터페이스 (stt, tts)
├── main_test.py        # [핵심] 프로젝트 통합 실행 파일
└── README.md           # 프로젝트 안내서
```
