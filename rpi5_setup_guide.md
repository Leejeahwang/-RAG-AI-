# Raspberry Pi 5 설치·실행 가이드 — 현재 통합 버전

2026-10-09 기준으로 main.py, main_test.py, config.py와 설치 목록을 대조한 안내입니다. 세부 이전·MeCab 설치 절차는 [raspberry_pi_migration.md](raspberry_pi_migration.md)를 함께 사용합니다. 실제 Pi 전체 설치·마이크·스피커·GPIO 검증은 아직 수행하지 않았습니다.

## 1. 코드와 실행 환경 준비

64-bit Raspberry Pi OS, aarch64, Python 3.11을 기준으로 준비합니다. Bookworm의 Python 3.11 환경을 기준으로 했으며 다른 OS/Python에서는 ARM wheel 제공 여부를 확인해야 합니다.

통합 버전은 `integration/vision-rag-voice` 브랜치입니다. 원격 feature/RAG만 clone하면 여기의 vision_bridge.py 및 통합 수정 사항은 포함되지 않습니다. 아래 브랜치를 복제하거나 현재 작업 폴더를 USB로 옮겨 사용합니다.

```bash
git clone --branch integration/vision-rag-voice https://github.com/Leejeahwang/-RAG-AI-.git
cd ./-RAG-AI-
```

함께 옮길 파일:

- main.py, main_test.py, vision_bridge.py, config.py, rag/, voice/, vision/, sensors/, alerts/, tools/ 및 requirements 파일
- data/ 전체와 같은 버전의 faiss_db/(없거나 오래되면 재구축 가능)
- models/ppaso/ 전체: config.json, example/, runtime/, 사전, ONNX 및 .onnx.data 파일
- vision/models/의 담당자가 준비한 화재·연기 가중치
- 설정 예시 .env.example. 실제 .env의 키는 별도로 관리

Windows .venv와 __pycache__는 복사해 사용하지 않습니다. SBERT와 Ollama 모델은 각각 HF 캐시와 Ollama 저장소에 있으므로 코드 폴더만 복사하면 오프라인 준비가 끝나지 않습니다.

```bash
uname -m
python3 --version
# 복사한 프로젝트 루트로 이동한 뒤 실행
ls main.py main_test.py vision_bridge.py requirements_rpi.txt
```

## 2. 시스템 패키지와 가상환경

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential git curl \
  portaudio19-dev libsndfile1 ffmpeg alsa-utils libopenblas-dev \
  libgl1 libglib2.0-0 swig liblgpio-dev
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r requirements_torch_cpu.txt
python -m pip install -r requirements_rpi.txt
python -m pip check
```

CPU PyTorch 설치가 성공한 뒤 공통 패키지를 설치합니다. 지원 wheel이 없다면 [공식 PyTorch 설치 안내](https://pytorch.org/get-started/locally/)에서 Python/아키텍처에 맞는 조합을 확인합니다. requirements는 버전 잠금 파일이 아니므로 설치 실패를 무시하고 다음 단계로 진행하지 않습니다.

OpenCV는 pip의 opencv-python 하나만 사용합니다. python3-opencv를 apt로 함께 설치하거나 headless 패키지를 추가하는 방식을 기본으로 안내하지 않습니다. 일반 venv는 시스템 Python 패키지를 자동으로 공유하지 않습니다.

FAISS는 Python 패키지 faiss-cpu가 필요합니다. libfaiss-dev만 설치해도 Python import faiss가 준비된다는 옛 안내는 잘못되었습니다. 호환 wheel이나 Python 바인딩을 포함한 설치 경로를 확인해야 합니다.

PYTTSX3 대체 음성을 사용할 때만 추가로 준비합니다:

```bash
sudo apt install -y espeak-ng libespeak-ng1 espeak-ng-data libespeak1
```

## 3. MeCab·PPASO·검색 모델 준비

```bash
python -c "from mecab import MeCab; print(MeCab().morphs('안전하게 대피하십시오'))"
python download_models.py --target ppaso
python download_models.py --target rag
python download_models.py --target ppaso --check
python download_models.py --target rag --check
python tools/rebuild_rag_index.py
```

이미 옮긴 PPASO 런타임이 있다면 다운로드보다 --check를 먼저 사용합니다. MeCab 형태소 분석이 실패하면 migration 가이드의 네이티브 설치 절차를 완료합니다. wheel은 대개 라이브러리를 포함하지만 지원되지 않는 조합에서는 직접 설치가 필요합니다. [공식 MeCab 안내](https://python-mecab-ko.readthedocs.io/en/latest/install/)

STT를 사용할 때만 모델을 별도로 준비합니다:

```bash
python download_models.py --target stt
python download_models.py --target stt --check
```

기본 모델은 small입니다. --target all은 PPASO/RAG만 준비하고 STT·Ollama·비전 모델은 포함하지 않습니다. USE_RERANKER=False가 기본이며, 켜려면 config.py 변경 후 --target rag로 BGE도 준비합니다.

## 4. Ollama와 앱 설정

Ollama가 없으면 [공식 설치 안내](https://ollama.com/download/linux)에 따라 설치합니다.

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:0.5b
ollama list
test -f .env || cp .env.example .env
nano .env
```

기본 응답 모델은 qwen2.5:0.5b이며 LLM_MODEL 환경변수로 변경할 수 있습니다. 1.5b는 선택 사항입니다. 현재 설정 예시:

```dotenv
AI_PROVIDER=local
LLM_MODEL=qwen2.5:0.5b
TTS_ENGINE=PPASO
STT_ENABLED=false
STT_WHISPER_MODEL=small
STT_LOCAL_FILES_ONLY=true
SENSOR_MODE=demo
ZONE_ID=A
```

Gemini를 사용하면 유효한 API 키와 계정에서 지원하는 GEMINI_MODEL을 설정하고 AI_PROVIDER=auto를 사용합니다. 키 교체 등 .env 변경 후 앱을 다시 실행합니다. SAPI5는 Windows 전용이며 Pi의 PYTTSX3는 pyttsx3 Linux 드라이버를 사용합니다.

## 5. 먼저 음성 경로 확인

```bash
python tools/diagnose_pi_tts.py --stage inspect
python tools/diagnose_pi_tts.py --stage synth
aplay scratch/pi_tts_probe.wav
python tools/diagnose_pi_tts.py --stage play
python tools/diagnose_pi_tts.py --stage project
```

각 명령을 별도로 실행하고 실제 소리가 들리는지 확인합니다. espeak가 들려도 PPASO 합성/pygame 재생은 실패할 수 있습니다. 단계별 해석은 [PI_TTS_DIAGNOSIS.md](PI_TTS_DIAGNOSIS.md)를 참고합니다. SDL_AUDIODRIVER=dummy로 실행하면 실제 스피커 검증이 되지 않습니다.

## 6. 평시 문답과 통합 실행

```bash
python main_test.py
# 위 프로그램을 q로 종료한 뒤
python main.py
```

main_test.py는 카메라를 실행하고 가상 센서로 상태를 표시하지만 비상 경보·대피 방송은 질문에 개입하지 않습니다. /ai local, /ai auto, /ai api, v, q를 사용하며 검색·답변·음성 시간을 표시합니다. 시작 시 STT를 준비하므로 마이크가 없으면 STT_ENABLED=false를 사용합니다.

main.py의 기본 SENSOR_MODE=demo도 가상 센서를 사용합니다. test fire는 데모 경보이며 첫 안내는 공통 고정 문구입니다. 이후 구역별 평면도와 매뉴얼로 추가 안내를 생성합니다. 특정 세 항목 형식이나 첫 안내의 구역 대피로 낭독을 보장하지 않습니다. 실제 비전 판정은 복원된 원본 코드의 결과를 사용합니다.

## 7. 실제 센서·카메라와 한글 표시

hardware 모드를 켜기 전에 담당자가 센서 배선과 드라이버를 확인합니다. MCP3008 연기·가스 입력은 SPI와 GPIO 접근 권한이 필요합니다. 온도 코드는 Adafruit_DHT.DHT11/GPIO4이며 구형 드라이버의 Pi 5 지원은 미검증이라 기본 설치 목록에서 제외했습니다. hardware 읽기 실패는 오류로 처리하며 가상 정상값으로 대체하지 않습니다. main_test.py는 이 설정과 무관하게 센서를 시뮬레이션합니다.

Camera Module 3 등 CSI 카메라는 먼저 Raspberry Pi 제공 CLI로 확인합니다. Bookworm부터 명칭은 rpicam-*입니다. [공식 카메라 문서](https://www.raspberrypi.com/documentation/computers/camera_software.html)

```bash
rpicam-hello --list-cameras
rpicam-jpeg -n -t 1000 -o /tmp/edge-saver-camera-test.jpg
```

원본 카메라 서비스는 Linux의 OpenCV 백엔드를 시도한 뒤 rpicam-jpeg 폴백을 사용합니다. CLI 성공만으로 프로젝트 캡처 성공이 보장되지는 않으므로 앱의 CAM 상태도 확인합니다. libcamerify는 환경별 선택 도구이며 완전 호환을 보장하지 않습니다. 복원된 비전 모델 우선순위는 OpenVINO → TFLite → ONNX → PT이며 기본 설치 목록은 ONNX/PT 실행을 준비합니다. 다른 형식의 런타임이나 배포 파일 변경은 비전 담당자와 확인하세요.

글자가 네모로 나오면 fonts-nanum을 설치합니다. 로케일이 필요하면 sudo dpkg-reconfigure locales에서 ko_KR.UTF-8을 선택하고 터미널을 다시 엽니다. SSH 터미널 글꼴은 접속 PC에서도 확인합니다.

## 8. 검증 범위

```bash
python -m unittest discover -s tests -q
python tools/check_rag_quality.py
```

유닛 테스트와 WAV 합성 성공은 실제 스피커·마이크·GPIO 확인을 대체하지 않습니다. 현재 통합 버전의 Windows 검증 기록은 INTEGRATION_RESULT.md에 있습니다. GUI는 구현 예정이므로 현재 실행 경로로 안내하지 않습니다.
