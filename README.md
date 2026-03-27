# 🚑 엣지 세이버(Edge Saver) - 지능형 재난 안전 RAG 시스템

이 프로젝트는 통신망이 단절된 극한의 재난 상황에서도 '국민재난안전포털'의 풍부한 가이드라인(HWP, PDF)을 바탕으로, 사용자에게 즉각적이고 정확한 행동 요령을 제공하는 **오프라인 특화형 RAG(Retrieval-Augmented Generation) AI 비서**입니다.

---

## 🏗️ 시스템 구성 (Module Details)

프로젝트는 모듈형 설계로 관리의 편의성을 높였으며, 각 폴더는 독립적인 역할을 수행합니다.

### 1. 전처리 파이프라인 (`rag/`)
재난 안전 데이터를 수집하고 AI가 읽기 쉬운 형태로 가공하는 핵심 엔진입니다.
- **`crawler.py`**: Selenium을 사용하여 재난안전포털의 게시판을 순회합니다. 중복 다운로드 방지 로직이 포함되어 있으며, 최신 매뉴얼을 `data/raw_documents`에 자동으로 저장합니다.
- **`parsing.py`**:
    - **HWP 파싱**: `pywin32`를 통해 설치된 한글 프로그램을 원격 제어하여 표(Table) 구조 등 텍스트를 정확하게 추출합니다.
    - **PDF 파싱**: `PyMuPDF`를 사용하여 텍스트 데이터를 확보합니다.
    - **AI 필터링**: Ollama(`qwen2.5:3b`)를 활용해 가이드라인이 아닌 홍보물, 단순 공지사항 등을 사전에 선별하여 데이터 품질을 높입니다.
- **`chunking.py`**: 추출된 긴 텍스트를 500자 단위로 정교하게 분할합니다. 100자의 중복 구간(Overlap)을 두어 검색 시 문맥이 끊기지 않도록 최적화합니다.

### 2. 지능형 음성 인터페이스 (`voice/`)
사용자와의 상호작용을 담당하는 오프라인 기반 보이스 엔진입니다.
- **`stt.py` (음성 인식)**: `faster-whisper` 모델을 사용하여 매우 낮은 지연 시간으로 음성을 텍스트로 변환합니다. **"세이버"**라는 호출어(Wake-word) 감지 후 명령을 수락하는 하이브리드 VAD 로직이 적용되어 있습니다.
- **`tts.py` (음성 합성)**: `pyttsx3`를 기반으로 한 오프라인 TTS 모듈입니다. Windows의 Heami 엔진이나 리눅스의 eSpeak를 자동 감지하며, AI의 복잡한 답변을 부드러운 한국어 음성으로 출력합니다.

### 3. 데이터 저장소 및 메인 로직 (`data/`, `main/`)
- **`data/`**: 시스템의 지식 베이스입니다. 원본 파일과 이를 전처리한 `parsed_manuals.json`, 최종 검색용 `chunked_manuals.json`이 통합 관리됩니다.
- **`main/`**: RAG 시스템의 작동을 테스트하는 환경입니다. `rag_test.py`는 LangChain을 통해 로컬 벡터 DB(Chroma)에 접속하고, AI 답변 생성과 TTS 음성 출력을 연결하는 통합 인터페이스를 제공합니다.

---

## 🛠️ 기술 스택 및 환경 설정

### 1. 주요 라이브러리 (Dependencies)
```bash
# RAG 및 AI
pip install langchain langchain-community chromadb requests
# 데이터 전처리
pip install selenium webdriver-manager beautifulsoup4 PyMuPDF pywin32
# 음성 처리
pip install numpy pyaudio faster-whisper pyttsx3
```

### 2. 로컬 LLM 환경
이 프로젝트는 개인정보 보호와 재난 상황 대응을 위해 **로컬 LLM**을 사용합니다.
1. [Ollama 공식 홈페이지](https://ollama.com/)에서 Ollama를 설치합니다.
2. 아래 명령어로 추론 및 필터링에 필요한 모델을 내려받습니다.
   ```bash
   ollama pull qwen2.5:1.5b  # 메인 추론용
   ollama pull qwen2.5:3b    # 데이터 전처리/필터링용 (선택 사항)
   ```

---

## 🚀 워크플로우 (How to Run)

1. **데이터 수집**: `python rag/crawler.py` 실행 (최신 매뉴얼 확보)
2. **데이터 변환**: `python rag/parsing.py` 실행 (텍스트 추출 및 AI 클리닝)
3. **데이터 최적화**: `python rag/chunking.py` 실행 (검색용 청크 생성)
4. **AI 비서 가동**: `python main/rag_test.py` 실행 (음성 대화 시작)

---

## 💡 프로젝트의 지향점
**엣지 세이버**는 '인터넷이 없는 환경에서도 생존할 수 있는 기술'을 지향합니다. 모든 프로세스는 로컬 하드웨어(노트북, 라즈베리 파이 5)에서 완결되도록 설계되었습니다.
