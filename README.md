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

Gemini 답변은 기본적으로 별도 명령 없이 Gemini TTS를 우선 사용하며, 실패 시 현재 로컬 엔진으로 전환합니다. 첫 비상 안내도 온라인 AI 모드에서는 Gemini TTS를 우선 사용합니다. `/ai local` 또는 로컬 TTS 고정에서는 첫 안내도 로컬 음성을 사용합니다. 등록 구역 안내(대피로·소화기 위치)도 Gemini TTS 우선으로 읽고 실패하면 로컬로 전환합니다. Ollama 답변은 로컬 음성을 사용하며, 비상 반복 방송은 처음 재생한 음성 파일을 재사용합니다. `/tts`로 정책과 최근 Gemini 실패 이유를 확인하고 `/tts auto`로 환경 설정의 기본 정책, `/tts ppaso` 또는 `/tts pyttsx3`로 로컬 고정을 선택합니다. 전환 시 기존 발화를 중단하며 실행 중인 LLM 답변은 유지합니다. 설정은 현재 실행에만 적용됩니다. 기존 `.env`에 `GEMINI_TTS_ENABLED=false`가 있으면 `true`로 변경하고 재시작하세요. 계속 로컬 음성을 원하면 `false`를 유지합니다. API만 시험하려면 `python tools/diagnose_gemini_tts.py --output gemini_tts_test.wav`를 실행하세요. TTS API 설정·Linux 시스템 음성·원격 오디오는 [raspberry_pi_migration.md](raspberry_pi_migration.md)를 참고하세요.

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
| `GEMINI_SEND_LAYOUT` | `true`; Gemini와 Ollama에 같은 구역 자료 전달. `false`이면 Gemini에는 검색 매뉴얼만 전달 |

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

라즈베리파이 부팅 자동 실행은 [자동 실행 설치 안내](docs/raspberry_pi_autostart.md)를 참고하세요. 프로젝트 가상환경에서 `python tools/install_autostart.py --start`를 한 번 실행하면 사용자 서비스로 등록합니다. `main.py --service`는 터미널 입력 없이 감지·비상 안내를 유지하며 기존 수동 실행과 구분합니다. 실제 Pi의 재부팅·장치 검증은 별도 확인이 필요합니다.

터미널과 질문 입력창을 함께 띄우려면 대신 `python tools/install_terminal_autostart.py --start`를 사용합니다. 기존 서비스를 중지·해제하고 데스크톱 로그인 시 LXTerminal에서 기존 `main.py`를 실행합니다. 로그인 없이 전원 부팅 후 창이 뜨려면 OS의 데스크톱 자동 로그인도 설정해야 합니다.

- 감시 스레드는 RAG·HTTP·음성 완료를 기다리지 않습니다.
- 첫 비상 안내는 고정 문구로 즉시 요청하고, 추가 안내는 별도 생성 작업에서 처리합니다.
- 정상 복귀 후에도 같은 비상의 후속 대피 지침은 한 번 출력·재생하고, 반복 방송은 종료합니다. 후속 안내가 끝나기 전에 같은 구역에서 재감지되면 기존 사건을 이어가며 검색·첫 안내를 다시 시작하지 않습니다. 다른 구역 경보가 추가되면 진행 중인 음성을 마친 뒤 통합 화재 목록으로 안내합니다. 안내 완료와 정상 복귀 후의 재감지는 새 사건으로 처리합니다. 한 번의 안내가 끝날 때까지 일반 질문은 받지 않습니다. 매뉴얼 근거 검증 또는 생성 실패 시 등록된 구역 안내는 유지됩니다.
- 이전 질문·종료된 경보의 늦은 결과를 발화하지 않습니다.
- PPASO 합성을 계산 중에 강제로 중단하지는 않습니다. 중단된 작업의 합성 결과를 재생하지 않고 다음 안내를 처리합니다.
- 관제 알림은 콘솔 출력이며, 장치 간 화재 경보는 아래 HTTP 설정으로 별도 연결합니다. GUI 통합은 후속 작업입니다.

기존 실행 코드와 인덱스의 복구 자료는 `scratch/integration_backup_20261009/`에 있습니다. 통합 결과와 검증 범위는 `INTEGRATION_RESULT.md`를 참고하세요.
## Ollama 비상 안내

비상 요청에서는 Ollama가 매뉴얼 문장 번호를 JSON으로 선택하고, 프로그램이 선택된 원문을 출력합니다. 긴 문장을 재작성하다 원문 검증에서 탈락하는 문제를 줄이기 위한 방식입니다. 현재 구역 파일의 명시된 1차·2차 대피로는 선택 결과에 유지합니다. 비상 요청의 생성 한도는 64토큰이며, 일반 문답의 기존 생성 방식은 유지합니다.

로그에 `[Ollama] 요청 시작`, `첫 응답 수신`, `응답 완료`가 표시됩니다. `[AI: fixed]`가 나오면 `[AI 전환 사유]`를 확인하세요. 스트림 미완료 또는 생성 한도 초과는 성공으로 처리하지 않습니다. 실행 중인 프로그램은 종료 후 다시 시작해야 변경 사항이 적용됩니다.

## 구역 안내와 추가 화재 대응 수칙

### Gemini 상황형 안내 (선택 기능)

`GEMINI_GUIDANCE_STYLE=contextual`로 설정하고 재시작하면 Gemini가 감지 정보·화재 구역·현재 안내 구역과 매뉴얼을 보고 필요한 수칙과 순서를 선택합니다. 구역 정보 전송을 허용한 경우 화재 구역의 용도·주의사항도 참고하지만, 이를 실제 발화 원인으로 확정하지 않습니다. 화재/안내 구역 문장은 프로그램이 확인된 이벤트 값으로 작성합니다. 원문 모드를 보존했으며 `GEMINI_GUIDANCE_STYLE=extractive`로 바꾸고 재시작하면 이전 Gemini 안내 방식으로 돌아갑니다. 설정을 생략해도 기존 방식입니다.

상황형 응답은 근거 수칙 번호와 안내 문장이 있는 JSON으로 받습니다. 근거 번호가 없거나 잘못된 JSON이면 기존 Ollama·고정 안내 경로로 전환합니다. 위치·숫자·방향·조건·금지·소화기 등 중요한 내용은 선택된 원문으로 복원합니다. 단순 일반 수칙은 검토한 표현 변형 범위에서 재표현을 허용하고, 그 범위를 벗어나면 원문을 사용합니다. 이는 임의의 자연어 사실을 완벽히 판별하는 검증기는 아닙니다. 따라서 자유로운 추론·새 경로 생성은 허용하지 않으며 표현 다양성은 제한적입니다.

첫 고정 안내와 등록 구역 대피로·소화기 위치는 AI를 기다리지 않는 기존 방식을 유지합니다. Ollama의 원문 선택 방식도 유지합니다. `GEMINI_SEND_LAYOUT=false`이면 추가 구역 용도 자료를 Gemini로 전송하지 않습니다.

2026-10-18 실제 Gemini 호출로 공장 매뉴얼과 A 화재/B 안내(원인 미확정) 상황을 시험했습니다. 첫 결과에서 여러 원인별 진압 수칙이 선택되어 프롬프트를 보완했으며, 재시험에서는 재진입 금지·엘리베이터 금지·집결지 인원 확인을 선택했습니다(약 1.83초). 단일 시험 사례이며 다양한 감지 상황과 Pi 음성 재생은 별도 검증이 필요합니다.

고정 구역 안내에는 현재 안내 구역의 대피로·주의사항 뒤에 소화기 위치와 데이터에 등록된 장비 종류도 포함됩니다. 원격 화재를 받아도 소화기 위치는 이 장치의 `ZONE_ID`에 해당하는 자료를 사용합니다. 장비 정보는 등록된 내용을 그대로 전달하며 화재별 적합성을 새로 추정하지 않습니다.

`main.py`는 첫 고정 비상 안내 다음에 설정된 구역 파일의 대피로와 주의사항을 출력하고 순서대로 재생합니다. 구역 안내는 검색 및 AI 성공 여부와 무관하게 예약됩니다. Gemini/Ollama는 별도로 검색한 화재 대응 매뉴얼에서 관련 원문 수칙을 선택하여 추가 안내합니다. 이미 안내한 동일 문장은 반복하지 않습니다. 정상 복귀 후에도 해당 사건의 예약된 안내를 마치며, 다른 구역의 새 비상이나 종료는 이전 안내를 중단합니다.

`main_test.py`의 일반 문답에서 Gemini는 원문 중심으로 설명하며 위치·소화기·대피로·조건·금지 사항의 생략과 과도한 요약을 피합니다. 기존 `.env`에 `GEMINI_SEND_LAYOUT=false`가 있으면 `true`로 바꿔야 Gemini도 직접 추가한 구역 자료를 받습니다. 실행 중 변경한 환경 설정은 프로그램 재시작 후 적용됩니다.

## 장치 간 HTTP 구역 경보

`ZONE_ID`는 이 장치가 설치된 구역입니다. 센서·카메라가 감시하는 구역은 `DETECTION_ZONE_ID`이며, 직접 감지한 화재는 이 값을 발생지로 전송합니다. 생략하면 `ZONE_ID`를 사용합니다. 수신 장치는 `fire_zone`을 별도로 보관합니다. 예를 들어 A 장치의 경보를 받은 B 장치는 **A구역 화재 / 현재 B구역**을 표시하고 B의 등록된 대피로를 안내합니다. 촬영·센서 감시 구역과 `DETECTION_ZONE_ID`를 맞추세요. 예를 들어 `ZONE_ID=B`, `DETECTION_ZONE_ID=A`이면 직접 감지 시에도 A 화재 발생지와 B 대피로·소화기 위치를 안내합니다. 두 설정은 재시작 후 적용됩니다.

첫 고정 안내도 발생지를 포함합니다. A 화재라면 `A구역에서 화재 위험이 감지되었습니다. 안전한 대피가 가능하면 즉시 대피하십시오. 대피가 어렵다면 119에 현재 위치를 알리고 구조를 요청하십시오.`를 출력하고 재생합니다. 원격 수신 시에도 현재 장치 구역이 아닌 화재 발생 구역을 말하며 반복 재생에도 유지합니다.

연결은 기본적으로 꺼져 있습니다. 각 장치의 `.env`에서 활성화하고 재시작하세요. 아래 IP는 예시이며 실제 주소로 바꿉니다.

```dotenv
# A 장치
ZONE_ID=A
ALERT_NODE_ID=device-A
ALERT_HTTP_ENABLED=true
ALERT_HTTP_HOST=0.0.0.0
ALERT_HTTP_PORT=8765
ALERT_HTTP_TOKEN=replace-with-a-shared-random-token
ALERT_HTTP_PEERS=http://192.168.45.12:8765
```

B 장치는 `ZONE_ID=B`, `ALERT_NODE_ID=device-B`, `ALERT_HTTP_PEERS=http://192.168.45.11:8765`로 설정하고 나머지는 동일하게 둡니다. 노드 ID는 장치마다 고유해야 하며 토큰은 동일해야 합니다. 여러 수신 주소는 쉼표로 구분합니다. 같은 LAN에서 TCP 8765 접근을 허용하세요. 이 HTTP 연결은 암호화되지 않으므로 신뢰하는 내부망에서만 사용합니다. 토큰은 Git에 올리지 않습니다.

발생 장치만 자신의 경보·정상 복귀를 전송하며 수신 이벤트를 다시 전달하지 않습니다. 수신 측 센서가 정상이어도 원격 화재는 해제되지 않습니다. 중복·역순 이벤트는 무시하고 최신 상태를 재전송합니다. 한 발생지의 해제가 다른 발생지의 경보를 해제하지 않습니다. 통신 단절이나 발생 장치 종료도 정상 복귀로 간주하지 않습니다. 발생 장치를 화재 중 재시작하면 기존 수신 경보가 남을 수 있으므로 현장 상태와 각 장치의 경보를 확인해야 합니다.

`SENSOR_MODE=demo`에서 `test fire`는 현장 화재를 발생시켜 설정된 상대 장치로도 전송합니다. `test fire A`는 이 장치에 A의 수신 경보를 흉내 내고 `test clear A`로 해제합니다. 구역을 붙인 테스트는 네트워크로 전달되지 않습니다.

같은 비상의 안내가 완료되면 기존 25초 반복 조건에 따라 저장된 음성을 재생하며 `[비상 안내 반복 재생]`과 안내 내용을 출력합니다. AI를 매번 다시 호출하지 않습니다. 정상 복귀 후 새 비상은 새 로그와 안내를 생성하고, 아직 진행 중인 같은 구역 안내는 이어갑니다.

등록된 대피로를 그대로 사용합니다. 화재 구역 접근 금지는 추가하지만, 구역 간 연결·통로 차단 자료가 없으므로 화재 구역을 통과하는 경로를 자동으로 재계산하지는 않습니다.

### 여러 구역의 동시 화재

로컬 감지와 수신 경보를 발생 장치별로 유지하고, 안내에는 중복 없는 화재 구역 목록을 사용합니다. A·C 화재를 B에서 수신하면 전체 화재 위치와 현재 안내 B구역을 구분하고, B의 등록된 대피로와 소화기 위치를 안내합니다. 같은 구역의 모든 발생 장치가 해제해야 그 구역을 목록에서 제외합니다. 통신 끊김은 해제가 아닙니다.

변경 경보는 1초 동안 모으고, 재생 중인 음성의 다음 쉼 구간에서 이전 안내와 대기열을 취소한 뒤 최신 목록으로 안내합니다. 16비트 PCM WAV에서 0.2초 이상 조용한 구간을 사용하며, 문장 의미를 인식하는 기능은 아닙니다. 적절한 쉼이 없거나 지원하지 않는 형식이면 현재 파일 끝에서 전환합니다. 변경이 취소되면 일시 정지했던 안내를 이어갑니다. 중간 상태가 다시 바뀌면 최종 목록만 사용합니다. 추가 감지·일부 해제 사실을 알린 뒤 현재 화재 목록을 안내하며 동일 상태의 재전송은 방송을 다시 시작하지 않습니다. 이전 상황에서 생성 중이던 AI 결과는 출력·재생하지 않습니다. 이미 전송한 API 요청 자체는 완료를 기다릴 수 있지만 새 목록의 고정 안내는 AI 생성 완료를 기다리지 않습니다. Gemini와 Ollama에는 전체 화재 목록과 구역별 감지 정보를 전달합니다.

상황 갱신 후에는 새 목록에 맞는 저장 음성으로 반복 방송합니다. 반복은 이전 반복 시작 이후 최소 25초가 지나고 안내 작업·음성이 끝났을 때 실행되며, 발화 종료 뒤 25초를 쉬는 방식은 아닙니다. 등록 경로가 여러 화재 때문에 막혔는지는 자동 판단하지 않으며 안전한 우회로를 생성하지 않습니다.

로컬 동작 비교는 `SENSOR_MODE=demo`에서 `test fire A`, `test fire C`, `test clear A`, `test clear C` 순서로 확인할 수 있습니다. 테스트 중 실제 카메라의 감지가 추가될 수 있으므로 콘솔의 전체 화재 목록을 함께 확인하세요.

첫 비상 안내의 텍스트는 즉시 출력하고, 음성은 Gemini TTS를 우선 준비합니다. 실패·키 없음·재시도 대기에서는 로컬 엔진으로 전환합니다. 사이렌 정지 요청은 첫 음성의 재생 시작을 SDL에서 확인한 뒤 보내며 기존 최소 유지 시간도 적용합니다. 이는 소프트웨어 재생 상태 확인이며 스피커에서 실제로 소리가 났다는 측정은 아닙니다. 파일 재생 오류는 같은 파일로 한 번 재시도합니다. 사이렌과 공유하는 mixer 전체를 종료하지 않고 음성 스트림만 다시 엽니다. 재시도도 실패하면 실패 로그를 남기며, 첫 음성이 시작되지 않았다면 사이렌 중지 요청을 보내지 않습니다. 정상 복귀·종료 시에는 강제로 정지합니다. 대피로와 소화기 위치는 등록된 문구를 유지하여 첫 음성 다음에 Gemini TTS 우선으로 재생하며, 실패하거나 `/ai local`·로컬 TTS 고정이면 로컬 엔진을 사용합니다. 실제 재생 엔진은 `[TTS] 재생 엔진` 로그로 확인합니다.

### 비상 음성 파일 재사용

한국어 발음·숫자 표기 교정은 [TTS 발음 교정 안내](docs/tts_pronunciation.md)를 참고하세요. CO2 등 로컬 엔진 발음과 거리·온도·퍼센트·범위 표기를 음성 입력에서만 정리하며, 원문과 검색 자료는 유지합니다. 비교 점검은 `python tools/audit_tts_pronunciation.py --audio`로 실행합니다.

첫 안내·구역 안내·추가 수칙은 합성 완료 후 사건별 임시 WAV로 보관합니다. 출력 장치 오류로 첫 재생에 실패해도 파일을 유지하여 다음 반복에서 다시 재생할 수 있습니다. 반복 방송은 이 파일들을 같은 순서로 재생하며 Gemini TTS와 로컬 합성을 다시 호출하지 않습니다. Gemini로 합성한 구간은 Gemini 목소리, 로컬로 대체한 구간은 해당 목소리를 유지합니다. 로그는 `[TTS] 저장 음성 재생: GEMINI` 또는 로컬 엔진을 표시합니다. 일반 문답은 저장하지 않습니다. 저장된 파일이 없으면 새 합성 대신 반복을 건너뛰고 로그로 알립니다.

Gemini TTS 우선 안내가 오류·재시도 대기로 로컬 음성으로 저장된 경우에는 별도 작업에서 Gemini 음성으로 다시 생성합니다. 실패 후 `GEMINI_TTS_RETRY_COOLDOWN`(기본 60초)이 지난 뒤 첫 안내·구역 안내·추가 수칙 순서로 한 구간씩 재시도하고, 성공한 경우에도 다음 구간 요청까지 같은 간격을 둡니다. 답변이나 검색을 다시 생성하지 않고, 로컬 발음 교정 전의 동일한 안내 문구를 Gemini TTS에 전달합니다. 합성 중에도 기존 파일로 방송하며, 성공한 파일은 다음 반복 시작 시 교체합니다. 현재 재생 중인 반복의 파일들은 그대로 유지합니다. 실패하면 기존 파일을 유지하고 다시 대기합니다. 준비·교체 로그는 `[TTS] Gemini 저장 음성 준비 완료`, `[TTS] 저장 음성 교체`로 표시합니다. 일반 문답·로컬 고정 안내는 재생성 대상이 아니며 `/ai local`, `/tts ppaso`, `/tts pyttsx3`에서는 재시도하지 않습니다. 비상 종료로 캐시를 정리하거나 사건·TTS 모드를 바꾸면 이전 요청 결과는 적용하지 않습니다. 이미 진행 중인 HTTP 요청 자체는 완료까지 기다릴 수 있습니다.

다른 사건 시작·안내 완료 후 정상 복귀·프로그램 종료 시 해당 캐시를 정리합니다. 정상 복귀 시에도 최초 안내가 진행 중이면 그 안내를 마친 뒤 정리합니다. 취소된 합성 결과는 캐시에 추가하지 않으며, 이전 사건의 정리 요청이 새 사건 캐시를 지우지 않도록 사건 번호를 검사합니다. 실행 중 TTS 모드 변경은 이후 합성에 적용되며, 이미 저장된 사건 음성의 목소리는 바꾸지 않습니다. 안내 사이에 인위적인 휴식 시간은 추가하지 않습니다.
