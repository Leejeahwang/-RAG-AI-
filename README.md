# 🔥 엣지 세이버 (Edge Saver)

> 멀티센서 + 카메라 AI + LLM/RAG를 결합한 **라즈베리파이 기반 지능형 화재 감시 시스템**

---

## 🚀 프로젝트 소개

연기·가스·온도 센서와 카메라 AI로 위험을 감시하는 **엣지 AI 화재 감시 시스템**입니다. 로컬 RAG가 매뉴얼을 검색하고, Gemini API 또는 로컬 Ollama가 검색 결과를 바탕으로 대응 안내를 생성합니다.

**핵심 차별점:**
- 🎯 **센서·영상 결합:** 센서 반응과 카메라 분석을 함께 사용해 위험을 판단
- 🧠 **매뉴얼 기반 안내:** 로컬에서 검색한 문서와 구역별 대피경로를 답변의 근거로 사용
- 📡 **연결 장애 대응:** 센서·영상 판정, 사이렌, 첫 비상 안내는 로컬에서 동작하며 Gemini 요청이 실패하면 Ollama로 전환
- 🔊 **로컬 음성 안내:** 기본 TTS 엔진으로 PPASO 사용

---

## 🛠️ 설치

[Ollama](https://ollama.com/)를 설치하고 실행한 뒤 로컬 답변 모델을 준비합니다.

Debian/Ubuntu에서 `requirements.txt`의 PyAudio를 빌드해 설치한다면 먼저 PortAudio 개발 패키지를 설치합니다. 이 패키지는 실행용 `libportaudio2`도 함께 설치합니다.

```bash
sudo apt install portaudio19-dev python3-dev
```

```bash
pip install -r requirements.txt

ollama pull qwen2.5:0.5b
```

검색어 재작성 기능이나 `rag/parser.py`의 AI 문서 정제를 사용할 경우 `qwen2.5:1.5b`도 준비합니다.

```bash
ollama pull qwen2.5:1.5b
```

PyTorch가 환경에 맞게 설치되지 않은 경우에는 사용 중인 OS와 GPU에 맞는 빌드를 설치하세요. 이미 설치된 PyAudio 실행 중 `libportaudio2`가 없다는 오류가 나면 `sudo apt install libportaudio2`로 실행용 라이브러리를 설치할 수 있습니다. 현재 `config.py`는 Linux에서 음성 인식(STT)을 기본적으로 비활성화합니다. 기본 음성 출력에는 `config.py`가 지정한 `models/ppaso` 모델 파일도 필요합니다.

---

## 🤖 AI 답변 설정

1. [Google AI Studio](https://aistudio.google.com/apikey)에서 Gemini API 키를 발급받습니다.
2. `.env.example`을 프로젝트 루트의 `.env`로 복사하고 `GEMINI_API_KEY`에 키를 입력합니다. `.env`는 Git에서 제외됩니다.
3. `.env`의 `AI_PROVIDER`로 시작 모드를 정합니다.

| `AI_PROVIDER` | 동작 |
|---|---|
| `auto` (기본값) | Gemini를 먼저 사용합니다. 키가 없거나 요청이 실패하면 Ollama로 전환하고, API 실패 후에는 일정 시간 재시도를 기다립니다. |
| `gemini` | 요청마다 Gemini를 우선 시도합니다. 실패하면 Ollama로 전환합니다. |
| `local` | 답변 생성에 Ollama만 사용합니다. |

실행 중 터미널(`main.py`, `main_test.py`)에서는 `/ai auto`, `/ai api`(`gemini`), `/ai local`로 전환할 수 있습니다. 대시보드에서는 **자동 / Gemini 우선 / 로컬 고정** 버튼을 사용합니다. 변경은 다음 요청부터 적용되며 재시작하면 `.env`의 설정으로 돌아갑니다.

질문이 들어오면 로컬 RAG가 매뉴얼을 검색하고, 선택한 모델이 검색 결과를 바탕으로 답합니다. Gemini에는 질문과 검색된 매뉴얼 내용이 전송됩니다. Gemini 답변이 검색 근거와 맞지 않거나 API 요청이 실패하면 Ollama로 전환합니다. 위험 감지 시 첫 비상 안내와 사이렌은 API 답변을 기다리지 않습니다.

`A구역 대피경로`처럼 구역과 경로를 명시한 질문에는 해당 `data/zone_*_layout.txt` 파일을 답변 문맥에 추가합니다. 구역을 특정하지 않으면 경로를 임의로 고르지 않습니다. 로컬 Ollama에는 이 정보가 제공되지만 Gemini 전송은 기본적으로 꺼져 있습니다. Gemini에도 보내려면 `.env`에 `GEMINI_SEND_LAYOUT=true`를 설정하고 앱을 재시작하세요. 현장 정보를 전송하기 전에 [Gemini API 요금과 데이터 사용 조건](https://ai.google.dev/gemini-api/docs/pricing)을 확인하세요.

## 🚀 실행 및 매뉴얼

```bash
python main.py
```

비상 경보 개입 없이 질문·답변을 확인하려면 `python main_test.py`를 실행합니다.

첫 실행에서 `faiss_db/` 인덱스가 없으면 `data/chunked_manuals.json`과 `data/` 하위 `.txt` 파일을 읽어 인덱스를 생성합니다. 인덱스가 이미 있으면 기존 것을 로드하므로 매뉴얼 파일만 추가하거나 바꿔도 검색 결과에 자동 반영되지는 않습니다. 현재 매뉴얼 재색인을 위한 별도 실행 명령은 없습니다.

음성 안내는 기본적으로 로컬 PPASO 엔진을 사용합니다. TTS 전처리에서 짧은 제목·항목의 줄 경계를 문장 사이 쉼으로 바꿔, PDF에서 추출된 제목과 본문이 붙어 발화되는 현상을 줄입니다.

---

## 📂 프로젝트 구조

```text
SW2026-2/
├── .env.example                 # Gemini 및 답변 모드 설정 예시
├── config.py                    # 센서·모델·TTS 설정
├── main.py                      # 통합 실행
├── main_test.py                 # 비상 경보 개입을 끈 테스트 실행
├── sensors/                     # 센서 수집과 위험도 계산
├── vision/
│   ├── cctv_service.py          # CCTV 영상 서비스
│   └── fire_detector.py         # 화재 영상 판별
├── rag/
│   ├── loader.py                # JSON·TXT 매뉴얼 로드
│   ├── native_retriever.py      # FAISS 검색 및 인덱스 생성
│   ├── layout.py                # 구역별 대피경로 선택
│   ├── provider.py              # Gemini/Ollama 선택과 장애 시 전환
│   └── chain.py                 # 로컬 Ollama 답변
├── voice/
│   ├── stt.py                   # 음성 인식
│   ├── tts.py                   # 음성 출력 및 발화 전처리
│   └── ppaso_wrapper.py         # PPASO 합성 엔진
├── gui/
│   ├── dashboard.py             # 관제 대시보드
│   ├── components.py            # 화면 구성 요소
│   ├── state.py                 # 화면 상태
│   └── workers.py               # 백그라운드 작업
├── data/
│   ├── raw_documents/           # 원본 매뉴얼
│   ├── chunked_manuals.json     # 가공된 매뉴얼 청크
│   └── zone_*_layout.txt        # 구역별 대피경로
├── faiss_db/                    # 로컬 검색 인덱스
└── alerts/                      # 사이렌·알림
```

---

## 💎 데이터 무결성 원칙 (Data Integrity Guard)

본 프로젝트의 RAG 지식 베이스는 **100% Plain Text**를 지향합니다.
- **Poison Pill 필터:** AI 파싱 단계에서 할루시네이션으로 발생하는 LaTeX 수식 기호(`$`, `\text{...}`)를 실시간 정규식으로 감지하고 강제 제거합니다.
- **화학식 평문화:** 모든 화학 반응식과 단위는 특수 기호 없이 표준 텍스트(예: NaHCO3, CO2)로만 저장되어 검색 정확도를 극대화합니다.

---

## 👥 팀원

| 이름 | 역할 | 담당 모듈 |
|------|------|-----------|
| 이재황 | PM & DevOps | `sensors/`, `alerts/`, `docker/`, RPi |
| 박규태 | Vision AI | `vision/`, `sensors/fusion.py` |
| 이승훈 | GUI & RAG Search | `gui/`, `rag/` |
| 채종화 | Voice & Data | `voice/`, `rag/parser.py`, `data/` |
