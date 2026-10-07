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

**라즈베리파이 설치·USB 이전은 [raspberry_pi_migration.md](raspberry_pi_migration.md)를 따르세요.** Pi에서는 가상환경에서 `python -m pip install -r requirements_rpi.txt`를 사용합니다. 이 파일은 공통 의존성과 GPIO 패키지를 함께 설치합니다.

[Ollama](https://ollama.com/)를 설치하고 실행한 뒤 로컬 답변 모델을 준비합니다.

Debian/Ubuntu에서 `requirements.txt`의 PyAudio를 빌드해 설치한다면 먼저 PortAudio 개발 패키지를 설치합니다. 이 패키지는 실행용 `libportaudio2`도 함께 설치합니다.

```bash
sudo apt install portaudio19-dev python3-dev
```

```bash
pip install -r requirements.txt

ollama pull qwen2.5:0.5b
```

PPASO 파일이 없으면 `python download_models.py --target ppaso`로 준비하고, 검색 모델은 `python download_models.py --target rag`로 캐시에 받습니다. 이미 옮긴 PPASO 파일은 `python download_models.py --target ppaso --check`로 확인할 수 있습니다. 파일 확인 후 실제 합성은 `python tools/benchmark_tts.py --engines ppaso --repeats 1`로 확인하세요. 다운로드 스크립트는 Ollama·영상 모델을 받지 않습니다.

준비된 JSON/TXT 매뉴얼 검색에는 OCR 패키지가 필요하지 않습니다. `rag/parser.py`로 원본 문서를 가공할 때는 `python -m pip install -r requirements_documents.txt`도 실행합니다.

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

터미널 질문 처리 후 `[시간] 검색 …초 / 답변 …초 / 음성 …초`가 출력됩니다. 검색은 RAG 호출, 답변은 Gemini·Ollama 호출(내부 전환 포함), 음성은 출력 요청부터 완료 대기까지의 시간입니다. 모델 초기화 시간은 별도이며, 음성 시간에는 실제 재생 시간이 포함됩니다. `main.py`의 자동 비상 알림 경로는 이 질문 처리 로그의 측정 대상이 아닙니다.

첫 실행에서 `faiss_db/` 인덱스가 없으면 `data/chunked_manuals.json`과 `data/` 하위 `.txt` 파일을 읽어 인덱스를 생성합니다. 인덱스가 이미 있으면 기존 것을 로드합니다. 문서가 변경되면 갱신 필요 메시지가 표시되며, 앱을 종료한 뒤 `python tools/rebuild_rag_index.py`로 인덱스를 백업하고 재구축합니다. `python tools/check_rag_quality.py`로 기본 검색 확인을 실행할 수 있습니다. BGE 재정렬 사용 여부는 `config.py`의 `USE_RERANKER`로 설정하며, 비교 측정 방법은 [RAG_BENCHMARK.md](RAG_BENCHMARK.md)를 참조하세요.

현재 BGE 재정렬은 기본으로 사용하되 `RERANKER_POLICY="selective"`로 명확한 CPR·출혈·골절 질문에 해당 근거가 확보된 경우 추론을 생략합니다. 구역·화재 등 다른 질문에는 계속 적용합니다. 모든 후보에 적용하려면 `RERANKER_POLICY="full"`로 바꾸고 재시작합니다. 모델은 계속 미리 로드하므로 추론 생략만으로 메모리가 줄지는 않습니다.

Windows PC의 28개 질문 근거 검색 시험에서 첫 번째 결과 적중은 BGE 끔 23/28, 전체 적용 28/28이었으며, 대표 검색 시간은 각각 약 0.039초와 2.696초였습니다. 이 수치는 최종 답변 정확도나 라즈베리파이 성능을 의미하지 않습니다. 조건·메모리·질문별 결과와 선택적 적용 후 확인은 [RAG_RERANKER_COMPARISON.md](RAG_RERANKER_COMPARISON.md)에 정리했습니다.

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

## TTS 벤치마크

`python tools/benchmark_tts.py --repeats 5`로 pyttsx3·PPASO·MeloTTS의 CPU 합성 시간, RTF, 최대 프로세스 메모리를 개별 측정할 수 있습니다. 결과는 `scratch/tts_benchmark/`에 CSV·JSON·WAV로 저장됩니다. 설치 준비와 Raspberry Pi 측정 시 주의사항은 [TTS_BENCHMARK.md](TTS_BENCHMARK.md)를 참고하세요.

## 👥 팀원

| 이름 | 역할 | 담당 모듈 |
|------|------|-----------|
| 이재황 | PM & DevOps | `sensors/`, `alerts/`, `docker/`, RPi |
| 박규태 | Vision AI | `vision/`, `sensors/fusion.py` |
| 이승훈 | GUI & RAG Search | `gui/`, `rag/` |
| 채종화 | Voice & Data | `voice/`, `rag/parser.py`, `data/` |
