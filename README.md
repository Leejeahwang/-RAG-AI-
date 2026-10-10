# Edge Saver — 비전 + RAG·음성 통합

현재 프로젝트의 경량 YOLO·Optical Flow·메모리 프레임 전달을 유지하고, `feature/RAG` 커밋 `ec99c872e9f2074a569d81db1dadd47f16ccc91c`의 검색·답변 공급자·음성 기능을 연결한 버전입니다.

## Windows 실행

이 작업 환경에는 프로젝트용 `.venv`와 PPASO 모델, 새 RAG 인덱스를 준비했습니다. `.venv`는 이 PC의 기존 Python 패키지를 공유하므로 다른 PC로 복사하지 말고 새로 만드세요.

```powershell
.\.venv\Scripts\python.exe main.py
```

명령:

- 일반 질문: 비전 감시와 별개로 RAG 답변 생성.
- `v` 또는 빈 입력: 마이크 질문. 첫 요청 시 Whisper 모델 로드.
- `/ai local`: Ollama 사용.
- `/ai auto`: Gemini 우선, 실패 시 Ollama 전환.
- `/ai api`: Gemini 우선 모드.
- `test fire`: 데모 비상 안내. 15초 동안 경보 복귀를 보류.
- `q`: 종료.

## 평시 문답 테스트

feature/RAG의 `main_test.py`를 현재 통합 모듈에 맞춰 가져왔습니다.

```powershell
.\.venv\Scripts\python.exe main_test.py
```

센서 값이 높아져도 비상 경보·대피 방송이 문답에 개입하지 않습니다. `/ai local`, `/ai auto`, `/ai api`, `v`, `q`를 사용할 수 있으며 검색·답변·음성 시간과 참고 문헌을 출력합니다. 이 모드는 센서를 시뮬레이션하고 카메라는 실행합니다. 원격 버전과 같이 시작 시 STT를 준비하므로 마이크를 쓰지 않으면 `.env`에 `STT_ENABLED=false`를 설정할 수 있습니다. reranker는 config.py의 설정을 따르며 기본 OFF입니다.

상태바는 입력 대기 중 0.5초마다 화면을 갱신합니다. 답변 생성·TTS 완료 대기는 별도 작업 스레드에서 처리하므로 답변 중에도 다음 질문을 입력할 수 있습니다. 새 질문을 제출하면 이전 음성을 중단하고 대기 중인 질문을 최신 질문으로 교체하며, 이전 생성 결과는 출력·발화하지 않습니다. 이미 진행 중인 HTTP 요청·합성 계산 자체는 즉시 취소하지 못할 수 있어 다음 답변 생성까지 기다릴 수 있습니다. 기존 감시 주기와 LLM 생성 중 감시를 쉬는 조건은 유지합니다.

## 새 환경 설치

Python 3.11 환경을 기준으로 검증했습니다.

Gemini TTS는 기본 비활성화 상태이며, Gemini 답변을 포함한 모든 안내는 `TTS_ENGINE`의 로컬 음성으로 읽습니다. 실행 중 `/tts`로 정책을 확인하고 `/tts auto`로 설정된 기본 정책, `/tts ppaso` 또는 `/tts pyttsx3`로 로컬 고정을 선택합니다. 전환 시 기존 발화를 중단하며 실행 중인 LLM 답변은 유지합니다. 설정은 현재 실행에만 적용됩니다. TTS API 설정·Linux 시스템 음성·원격 오디오는 [raspberry_pi_migration.md](raspberry_pi_migration.md)를 참고하세요.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe download_models.py --target ppaso
.\.venv\Scripts\python.exe download_models.py --target rag
.\.venv\Scripts\python.exe download_models.py --target stt
.\.venv\Scripts\python.exe tools/rebuild_rag_index.py
```

Ollama 답변을 사용하려면 Ollama 서버를 실행하고 `qwen2.5:0.5b`를 준비하세요. API 키가 없으면 Gemini에 요청하지 않고 Ollama를 사용합니다. 두 공급자를 모두 사용할 수 없는 긴급 상황에는 고정 첫 안내를 유지합니다. 일반 질의는 답변 생성 실패를 표시합니다.

```powershell
ollama pull qwen2.5:0.5b
```

`.env.example`을 참고해 `.env`에 필요한 설정을 작성할 수 있습니다. 기존 `.env`가 있다면 필요한 항목만 병합하세요.

| 설정 | 기본 동작 |
|---|---|
| `AI_PROVIDER` | `auto`; 키가 없으면 로컬 전환 |
| `TTS_ENGINE` | `PPASO`; 초기화 불가 시 실제 엔진을 표시하고 시스템 TTS 전환 |
| `STT_WHISPER_MODEL` | `small`; 배포 환경별 변경 가능 |
| `STT_ENABLED` | Windows 활성화, Linux 비활성화 |
| `STT_LOCAL_FILES_ONLY` | `true`; 실행 중 자동 다운로드하지 않음 |
| `SENSOR_MODE` | `demo`; `hardware`는 실제 센서 사용 |
| `DEMO_VISION_ESCALATION` | `true`; 데모에서 원본 감지기의 `fire_detected` 결과(실연기 표시 제외)로 가상 센서 격상 |
| `ZONE_ID` | `A`; 설치 구역으로 변경 |
| `GEMINI_SEND_LAYOUT` | `false`; 로컬 평면도의 클라우드 전송 제어 |

`STT_ENABLED=true`를 Pi에 적용하려면 실제 마이크·ALSA·지연·메모리를 별도로 확인해야 합니다. 마이크나 캐시 모델이 없으면 텍스트 입력을 계속 사용할 수 있습니다.

실제 센서를 사용하는 `hardware` 모드에서는 센서 실패를 가상 정상값으로 대체하지 않습니다. GPIO 드라이버·ADC 연결을 준비한 뒤 활성화하세요. `test fire`와 가상 센서 상승은 `demo` 모드에서만 동작합니다.

## Raspberry Pi 설치

64-bit Raspberry Pi OS와 Python 3.11을 기준으로 가상환경을 만들고 CPU PyTorch와 공통 패키지를 설치합니다. 통합 버전은 `integration/vision-rag-voice` 브랜치를 사용합니다. PPASO·검색·STT 모델 캐시와 개인 설정은 별도로 준비합니다. Windows 가상환경은 복사하지 않습니다. 상세 설치·MeCab 문제 해결은 [raspberry_pi_migration.md](raspberry_pi_migration.md), Pi 5 실행 순서는 [rpi5_setup_guide.md](rpi5_setup_guide.md)를 따르세요.

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential git curl \
  portaudio19-dev libsndfile1 ffmpeg alsa-utils libopenblas-dev \
  libgl1 libglib2.0-0 liblgpio-dev swig
python3.11 -m venv .venv-py311
.venv-py311/bin/python -m pip install -r requirements_torch_cpu.txt
.venv-py311/bin/python -m pip install -r requirements_rpi.txt
.venv-py311/bin/python download_models.py --target ppaso
.venv-py311/bin/python download_models.py --target rag
.venv-py311/bin/python tools/rebuild_rag_index.py
.venv-py311/bin/python main.py
```

PPASO의 한국어 G2P는 `from mecab import MeCab`로 실제 형태소 분석까지 확인해야 합니다. 지원 wheel이 없다면 [MeCab 공식 소스 설치 안내](https://python-mecab-ko.readthedocs.io/en/latest/install/)와 migration 가이드의 네이티브 설치 절차를 사용합니다. Linux 시스템 음성 대체 경로가 필요하면 `sudo apt install -y espeak-ng libespeak-ng1 espeak-ng-data libespeak1`을 추가합니다. espeak 성공과 PPASO·pygame 재생 성공은 별도이며 `tools/diagnose_pi_tts.py`로 합성과 재생을 나눠 확인합니다.

실제 온도 센서는 현재 `Adafruit_DHT.DHT11`/GPIO4이며 이 구형 드라이버의 Pi 5 호환성은 미검증입니다. 기본 설치 목록에 자동으로 추가하지 않았습니다. `hardware` 모드는 드라이버·배선 검증 후 사용하세요. 현재 Windows에서 수행한 성능·음성 검증을 Pi 결과로 해석하지 마세요. STT 모델이 필요하면 별도로 `--target stt`를 실행합니다. `--target all`은 PPASO와 RAG만 준비합니다.

비전 소스와 센서 퓨전은 통합 전 버전으로 복원했습니다. Windows import 호환성과 프레임 중복 확인은 `vision_bridge.py`가 담당합니다. 상세 복원 범위는 INTEGRATION_RESULT.md를 참고하세요.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe vision/test_unit_verification.py
.\.venv\Scripts\python.exe tools/check_rag_quality.py
.\.venv\Scripts\python.exe tools/benchmark_tts.py --engines ppaso --repeats 1
.\.venv\Scripts\python.exe tools/smoke_integration.py
.\.venv\Scripts\python.exe tools/check_local_guidance.py
```

`smoke_integration.py`는 실제 YOLO·RAG·TTS 모델을 사용하고, 카메라에는 검정 합성 프레임을 공급하며 SDL 무음 출력으로 재생을 검증합니다. 실제 카메라·스피커·마이크 테스트를 대신하지 않습니다. 로컬 공급자만 사용하므로 클라우드에 요청하지 않습니다.

합성 WAV로 오프라인 STT를 확인하려면:

```powershell
.\.venv\Scripts\python.exe tools/check_voice_roundtrip.py --model small --audio scratch/integration_tts_benchmark/ppaso/text_1_repeat_1.wav
```

문서를 변경하면 다음 기동 시 변경을 감지해 인덱스를 백업·재구축합니다. 수동 갱신은 `tools/rebuild_rag_index.py`를 사용하세요.

## 선택 의존성

- 기본 `requirements.txt`: CLI·현재 비전·FAISS/BM25·PPASO·Whisper 실행과 WAV 검증용 SciPy.
- `requirements_torch_cpu.txt`: 새 CPU 환경에서 공통 패키지보다 먼저 설치.
- `requirements_rpi.txt`: 공통 패키지와 MCP3008용 GPIO 패키지.
- `requirements_documents.txt`: 원본 PDF/OCR 재가공용 PyMuPDF·EasyOCR. 준비된 TXT/JSON 검색에는 불필요.
- `requirements_benchmarks.txt`: 과거 Chroma 비교 벤치마크에만 필요한 chromadb.
- MeloTTS는 선택 엔진이며 기본 PPASO 실행 의존성에 포함하지 않음. 사용하려면 [공식 설치 안내](https://github.com/myshell-ai/MeloTTS/blob/main/docs/install.md)에 따라 별도 환경을 준비.
- GUI는 구현 예정이므로 streamlit/pandas를 기본 실행 의존성에서 제외.

requirements는 완전한 버전 잠금 파일이 아니며 새 ARM 환경의 설치 완료를 보장하지 않습니다.

## 통합 범위와 복구

- 감시 스레드는 RAG·HTTP·음성 완료를 기다리지 않습니다.
- 첫 비상 안내는 고정 문구로 즉시 요청하고, 추가 안내는 별도 생성 작업에서 처리합니다.
- 정상 복귀 후에도 같은 비상의 후속 대피 지침은 한 번 출력·재생하고, 반복 방송은 종료합니다. 새 비상이 발생하면 이전 안내를 취소합니다. 한 번의 안내가 끝날 때까지 일반 질문은 받지 않습니다. 매뉴얼 근거 검증 또는 생성 실패 시 구체적인 대피로 대신 고정 안내가 유지될 수 있습니다.
- 이전 질문·종료된 경보의 늦은 결과를 발화하지 않습니다.
- PPASO 합성을 계산 중에 강제로 중단하지는 않습니다. 중단된 작업의 합성 결과를 재생하지 않고 다음 안내를 처리합니다.
- 현재 관제 알림은 콘솔 출력이며 외부 관제 전송과 GUI 통합은 후속 작업입니다.

기존 실행 코드와 인덱스의 복구 자료는 `scratch/integration_backup_20261009/`에 있습니다. 통합 결과와 검증 범위는 `INTEGRATION_RESULT.md`를 참고하세요.
