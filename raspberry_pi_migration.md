# 라즈베리파이 설치·이전 가이드 — 현재 통합 버전

2026-10-09 설치 문서 대조 반영. 통합 버전은 아래의 integration/vision-rag-voice 브랜치로 가져옵니다. 모델 캐시와 개인 설정은 별도로 준비해야 합니다. 상세 차이는 INTEGRATION_RESULT.md를 참고하세요.

프로젝트 루트에서 실행합니다. 64비트 Raspberry Pi OS와 충분한 저장 공간을 준비하세요. Python 의존성, 모델 파일, 시스템 라이브러리는 각각 필요합니다. 아래 명령은 Pi 터미널용입니다.

## 1. 프로젝트 가져오기

USB로 최신 프로젝트를 옮겼다면 해당 폴더에서 시작합니다.

```bash
cd /home/raspi/Desktop/SW2026-2
```

Git을 사용할 때는 작업 브랜치를 지정합니다. 아직 Git에 올리지 않은 PC 수정 사항은 USB로 옮겨야 합니다.

```bash
cd ~/Desktop
git clone --branch integration/vision-rag-voice https://github.com/Leejeahwang/-RAG-AI-.git SW2026-2
cd SW2026-2
```

이미 같은 이름의 폴더가 있으면 clone 대신 기존 폴더를 사용하세요.

USB 복사 후 필수 코드가 빠지지 않았는지 확인합니다.

```bash
test -f rag/__init__.py && test -f rag/native_retriever.py && echo 'rag files ok'
```

`rag files ok`가 나오지 않으면 최신 프로젝트의 `rag/` 폴더를 복원하세요. `No module named 'rag'`는 코드 누락 문제이며 패키지 설치나 모델 다운로드로 해결되지 않습니다.

### USB에 함께 넣을 파일

- 프로젝트 코드, requirements 파일, `config.py`
- `data/` 전체, `faiss_db/` 전체(매뉴얼과 인덱스가 같은 버전이어야 함)
- `models/ppaso/` 전체: ONNX 가중치뿐 아니라 `example/`, `runtime/`, 사전, `config.json`도 필요
- `vision/models/`의 화재·연기 전용 모델. 기본 YOLO 모델로 대체하면 안 됨
- Gemini를 사용할 경우 직접 관리하는 `.env`(API 키 포함, Git에 올리지 않음)

Windows의 `venv`, `.venv`, `__pycache__`는 옮겨서 사용하지 않습니다. Pi에서 이미 동작하는 기존 가상환경은 원래 위치에 두고 활성화해 새 프로젝트를 실행할 수 있지만 추가 의존성은 설치해야 합니다.

완전한 오프라인 실행에는 SBERT/BGE의 Hugging Face 캐시와 Ollama 모델도 필요합니다. 기본 HF 위치는 `~/.cache/huggingface/hub`이며 설정에 따라 달라집니다. 캐시를 옮길 때 실제 가중치와 링크 대상까지 포함하세요. Ollama 모델은 서비스 계정·`OLLAMA_MODELS` 설정에 따라 저장 위치가 다르므로 기존 Pi 모델을 유지하거나 온라인에서 아래 모델을 먼저 받으세요. Windows의 Python 패키지와 Ollama 실행 바이너리는 Pi용으로 다시 설치해야 합니다.

## 2. 시스템 패키지

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential git curl \
  portaudio19-dev libsndfile1 ffmpeg alsa-utils libopenblas-dev libgl1 libglib2.0-0 swig liblgpio-dev
```

PyAudio 빌드에는 `portaudio19-dev`가 필요합니다. 실행용 `libportaudio2`만 설치하면 개발 헤더가 부족할 수 있습니다.

GPIO용 Python `lgpio`를 소스 빌드할 때는 `liblgpio-dev`가 필요합니다. `/usr/bin/ld: cannot find -llgpio`는 용량 부족이 아니라 링크할 native 라이브러리가 없다는 뜻입니다. `sudo apt install -y liblgpio-dev`가 성공한 뒤 활성화된 가상환경에서 `python -m pip install -r requirements_rpi.txt`를 다시 실행합니다.

pyttsx3 비교 시험을 할 경우 추가 설치합니다(PPASO 합성에는 eSpeak가 필요하지 않음).

```bash
sudo apt install -y espeak-ng libespeak-ng1 espeak-ng-data libespeak1
```

## 3. 가상환경과 Python 패키지

새 환경을 만드는 경우:

```bash
python3 -m venv .venv
source .venv/bin/activate
python --version
python -c "import sys; assert sys.prefix != sys.base_prefix, '가상환경이 활성화되지 않았습니다'; print(sys.executable)"
python -m pip install --upgrade pip wheel
python -m pip install -r requirements_torch_cpu.txt
python -m pip install -r requirements_rpi.txt
```

이미 동작하는 Pi 환경을 재사용하는 경우에는 첫 두 명령 대신 그 환경의 `bin/activate`를 지정합니다. 예:

```bash
source /home/raspi/Desktop/RAG/-RAG-AI-/.venv/bin/activate
cd /home/raspi/Desktop/SW2026-2
python -m pip install -r requirements_rpi.txt
```

명령은 순서대로 실행하고, 오류가 나면 다음 단계로 넘어가지 않습니다. `No space left on device`가 뜨면 `df -h .`로 공간을 확인하고 먼저 확보하세요. 가상환경 생성이 실패하면 `bin/activate`도 없을 수 있습니다. 이 상태에서 pip를 실행하면 시스템 Python의 `externally-managed-environment` 오류가 이어질 수 있으므로 가상환경 생성·활성화부터 다시 확인합니다.

`requirements_rpi.txt`는 공통 `requirements.txt`와 GPIO 패키지를 함께 설치합니다. 새 환경에서는 반드시 앞 단계의 CPU PyTorch 설치가 성공한 뒤 진행하세요. `requirements_torch_cpu.txt`는 [PyTorch 공식 CPU 인덱스](https://pytorch.org/get-started/locally/)를 지정합니다. 호환 wheel이 없으면 Python 버전과 `uname -m` 출력(aarch64)을 확인하고, 일반 PyPI GPU 빌드로 우회하지 마세요. 기존 CUDA 빌드를 CPU 빌드로 교체하는 작업은 새 환경 설치와 별개입니다.

OpenCV는 일반 `opencv-python`만 사용합니다. Roboflow SDK는 현재 앱에서 사용하지 않고 headless OpenCV를 추가 설치하므로 기본 목록에서 제외했습니다. 데이터셋 작업에 필요하면 별도 작업 환경에 설치하세요. 설치가 실패하면 마지막 오류를 해결한 뒤 다시 설치합니다. FAISS의 Python 모듈은 `faiss-cpu`입니다. `libfaiss-dev`만 설치하는 것으로 Python `import faiss`를 대체할 수 없습니다.

Python 3.13에서 ARM64 wheel이 없는 패키지는 소스 빌드로 넘어갈 수 있습니다. 해당 오류가 발생하면 패키지 지원 버전을 확인하고 별도 Python 3.11 환경을 고려하세요. OS에 따라 `apt install python3.11`은 제공되지 않을 수 있습니다. 현재 동작하는 환경을 지우지는 마세요. 이 목록은 버전 잠금 파일이 아니므로 새 설치의 모든 조합을 보장하지 않습니다.

원본 PDF/OCR 문서를 다시 가공할 때만 추가 설치:

```bash
python -m pip install -r requirements_documents.txt
```

MeloTTS는 기본 앱의 필수 패키지가 아닙니다. 선택해서 사용할 경우 [공식 설치 안내](https://github.com/myshell-ai/MeloTTS/blob/main/docs/install.md)에 따라 별도 환경을 준비하세요.

## 4. PPASO·검색 모델 준비

USB로 모델을 옮겼으면 먼저 파일을 확인합니다(다운로드 없음).

```bash
python download_models.py --target ppaso --check
```

PPASO 파일이 없을 때만 인터넷에 연결해 받습니다. 기존 런타임을 수정한 경우에는 다운로드로 덮어쓰지 말고 해당 수정본을 옮기세요.

```bash
python download_models.py --target ppaso
python download_models.py --target rag
```

다운로드 파일은 `config.PPASO_MODEL_DIR`(기본 `models/ppaso`)에, 검색 모델은 Hugging Face 캐시에 저장됩니다. SBERT와 `USE_RERANKER=True`일 때 BGE를 준비합니다. Ollama와 화재 영상 모델은 이 스크립트가 받지 않습니다. STT는 별도 `python download_models.py --target stt`로 준비합니다. 기본 모델은 small이며, `--target all`에는 STT 다운로드가 포함되지 않습니다. 실행 중 STT 자동 다운로드는 기본 비활성화입니다.

현재 BGE 재정렬은 Pi 검색 지연 비교를 위해 기본 비활성화(`USE_RERANKER=False`)입니다. FAISS·BM25 검색은 계속 사용합니다. 품질 비교를 위해 BGE를 켜려면 `config.py`를 변경하고 `python download_models.py --target rag`로 모델을 준비한 뒤 앱을 재시작하세요.

### MeCab 확인 및 새 환경의 네이티브 설치

```bash
python -c "from mecab import MeCab; print(MeCab().morphs('안전하게 대피하십시오'))"
```

단어 목록이 나오면 이 설치 단계는 건너뜁니다. `requirements` 설치 성공이나 `Requirement already satisfied`만으로 MeCab 동작을 판단하지 않습니다. Python 패키지가 있어도 네이티브 라이브러리가 없을 수 있습니다. 기존 가상환경을 삭제하고 새로 만들었다면 이전 환경 내부의 라이브러리도 다시 설치해야 합니다.

다음 오류는 **한국어 mecab-ko** 네이티브 설치가 필요한 경우입니다.

- `mecab-config not found`: 소스 빌드에 필요한 도구를 찾지 못함
- `ImportError: libmecab.so.2 ... No such file or directory`: 라이브러리가 없거나 로딩 경로가 맞지 않음

두 번째 오류라면 활성화된 가상환경에서 먼저 위치를 확인합니다.

```bash
find "$VIRTUAL_ENV" /usr/local/lib /usr/lib -name 'libmecab.so*' 2>/dev/null
```

경로가 나오면 해당 설치의 라이브러리 경로를 확인합니다. 아무 경로도 나오지 않으면 아래 절차로 현재 가상환경에 설치합니다. 일본어용 `mecab-python3`는 PPASO 의존성을 대체하지 않습니다. 아래는 [공식 설치 스크립트](https://raw.githubusercontent.com/jonghwanhyeon/python-mecab-ko/main/scripts/install_mecab_ko.py)의 `--prefix` 옵션을 사용합니다.

```bash
sudo apt install -y build-essential python3-dev curl
curl -fL https://raw.githubusercontent.com/jonghwanhyeon/python-mecab-ko/main/scripts/install_mecab_ko.py -o /tmp/install_mecab_ko.py
```

기존 GNU Savannah HTTP 주소에 연결하지 못했던 경우를 위해 `config.guess`와 `config.sub` 다운로드 주소를 GCC 저장소의 HTTPS 주소로 변경합니다.

```bash
python - <<'PY'
from pathlib import Path

p = Path("/tmp/install_mecab_ko.py")
s = p.read_text()
for name in ("guess", "sub"):
    old = f"http://git.savannah.gnu.org/gitweb/?p=config.git;a=blob_plain;f=config.{name};hb=HEAD"
    new = f"https://raw.githubusercontent.com/gcc-mirror/gcc/master/config.{name}"
    s = s.replace(old, new)
p.write_text(s)
PY

python /tmp/install_mecab_ko.py --prefix "$VIRTUAL_ENV"
```

설치 명령이 오류 없이 끝난 뒤 경로를 설정하고 Python 바인딩을 새 환경 기준으로 다시 빌드합니다. 이전 환경에서 빌드한 캐시 wheel을 재사용하지 않도록 합니다.

```bash
export PATH="$VIRTUAL_ENV/bin:$PATH"
export LD_LIBRARY_PATH="$VIRTUAL_ENV/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
python -m pip install --force-reinstall --no-cache-dir --no-binary=python-mecab-ko python-mecab-ko
python -c "from mecab import MeCab; print(MeCab().morphs('안전하게 대피하십시오'))"
```

단어 목록이 나와야 다음 단계로 진행합니다. 설치 스크립트 다운로드 중 `Network is unreachable`이 뜨면 해당 호스트 연결 실패이며 설치 성공으로 볼 수 없습니다. `make`의 '할 일이 없습니다'는 그 자체로 오류가 아닙니다.

**새 터미널을 열 때도** 환경을 활성화한 뒤 다음 두 경로 설정을 적용하고 앱을 실행합니다. `export` 설정은 현재 셸에만 적용되며, 가상환경을 활성화하는 것만으로 자동 복원되지 않습니다.

```bash
source .venv/bin/activate
export PATH="$VIRTUAL_ENV/bin:$PATH"
export LD_LIBRARY_PATH="$VIRTUAL_ENV/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

## 5. Ollama·Gemini 설정

Ollama가 없다면 [공식 설치 안내](https://ollama.com/download/linux)에 따라 설치합니다.

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:0.5b
ollama list
```

현재 답변 모델은 `qwen2.5:0.5b`입니다. 검색어 재작성이나 AI 문서 정제를 사용할 때만 `qwen2.5:1.5b`도 받으세요. Ollama 서비스가 실행되어 있어야 로컬 답변을 생성할 수 있습니다.

기존 `.env`가 없을 때만 예시를 복사하고 편집합니다.

```bash
test -f .env || cp .env.example .env
nano .env
```

`GEMINI_API_KEY`와 사용 가능한 `GEMINI_MODEL`, `AI_PROVIDER=auto` 또는 `local`을 설정합니다. API 키가 없어도 로컬 모드를 사용할 수 있습니다.

## 6. 실행 전 확인

```bash
python -c "import cv2, faiss, onnxruntime, soundfile, scipy, pygame, gpiozero; print('imports ok')"
python download_models.py --target rag --check
python tools/benchmark_tts.py --engines ppaso --repeats 1
python tools/check_rag_quality.py
python main_test.py
```

PPASO 파일 확인 성공은 음성 합성 성공을 뜻하지 않습니다. 벤치마크의 `ppaso: ok`와 생성 WAV까지 확인하세요. 실패 원인은 출력된 결과 폴더의 `ppaso/worker.log`에서 확인합니다. 스피커 재생은 `main_test.py`에서 별도로 확인합니다.

문서 변경 경고가 나오면 앱을 종료하고 인덱스를 갱신합니다.

```bash
python tools/rebuild_rag_index.py
```

확인 후 통합 실행:

```bash
python main.py
```

평시 문답만 확인할 때는 `python main_test.py`를 사용합니다. 카메라는 실행하지만 센서는 시뮬레이션하며 비상 경보·대피 방송 개입을 끕니다. 두 앱을 동시에 실행하지 않습니다. GUI는 현재 구현 예정인 별도 모듈이므로 실행 안내와 streamlit/pandas 설치를 제외했습니다. Linux에서 STT는 기본 비활성화됩니다.

## 7. 실제 센서와 영상 점검

- 연기·가스 센서는 `gpiozero.MCP3008`을 사용합니다. SPI 활성화, ADC 배선·채널, GPIO 접근 권한을 확인하세요. Pi 설정에서 SPI를 활성화하고 재부팅합니다.
- 온도 센서 코드(`sensors/temperature.py`)는 현재 `Adafruit_DHT.DHT11`과 GPIO 4를 사용합니다. DHT22로 설명한 옛 가이드는 맞지 않습니다. 이 구형 드라이버의 Pi 5 지원은 별도 검증·수정이 필요합니다. 패키지 설치만으로 실제 센서 동작을 보장하지 않습니다.
- 현재 main.py는 기본 SENSOR_MODE=demo이며 가상 값을 사용합니다. hardware 모드에서는 센서 읽기 실패를 RuntimeError로 처리하고 오류를 표시하며 가상 정상값으로 대체하지 않습니다. main_test.py는 SENSOR_MODE와 무관하게 센서를 시뮬레이션합니다.
- 현재 사이렌은 pygame 오디오 출력입니다. 옛 가이드의 `ALERT_BUZZER_PIN`, `ALERT_LED_PIN`은 현재 설정 항목이 아닙니다.
- 복원된 `vision/fire_detector.py`의 모델 선택 순서는 OpenVINO → TFLite → ONNX → PT입니다. 기본 requirements에는 ONNXRuntime과 PyTorch만 준비합니다. 다른 형식은 각 실행 라이브러리가 별도로 필요합니다. Pi에서는 담당자와 합의한 모델 형식과 배포 파일을 사용하고, 모델 선택 로직이나 가중치를 임의로 수정하지 마세요.

폰트가 깨지면 `sudo apt install fonts-nanum`을 사용합니다. 모델·센서·스피커 확인은 실제 Pi에서 수행해야 합니다.

## 8. 음성 출력과 설정 확인

기본 TTS는 PPASO 합성 후 pygame 재생입니다. 터미널 espeak 성공만으로 이 경로를 검증할 수 없습니다. 현재 통합 TTS는 PPASO 초기화 실패 시 PYTTSX3로 전환하고 실제 엔진을 표시합니다. Linux 시스템 음성은 pyttsx3이며 SAPI5는 Windows 전용입니다. 한국어 시스템 목소리가 없으면 오류를 표시합니다.

```bash
python tools/diagnose_pi_tts.py --stage inspect
python tools/diagnose_pi_tts.py --stage synth
aplay scratch/pi_tts_probe.wav
python tools/diagnose_pi_tts.py --stage play
python tools/diagnose_pi_tts.py --stage project
```

각 명령은 따로 실행합니다. synth 실패는 PPASO 모델/의존성부터, aplay 성공 후 play 실패는 SDL/pygame 출력 경로부터 확인합니다. 상세 판정은 PI_TTS_DIAGNOSIS.md를 참고하세요. 무음 진단 때 프로젝트를 먼저 종료하고 동일 사용자와 가상환경을 사용합니다.

.env 예시는 demo 센서 모드, PPASO, Whisper small, 구역 A입니다. 현장의 ZONE_ID와 평면도를 검토하세요. Gemini 키와 모델은 본인 계정에서 사용 가능한 값으로 설정합니다. HTTPError가 있으면 API 응답의 상태 코드와 오류를 확인해야 하며, 기존에 확인한 무효 키 오류는 키 교체와 프로그램 재시작이 필요합니다. 로컬 확인은 /ai local을 사용합니다. 첫 비상 안내는 공통 고정 문구이고 구역 대피로는 후속 생성 컨텍스트에 포함됩니다. 세 항목 형식의 출력이나 첫 안내에서 구역 대피로 낭독을 보장하지 않습니다.

## 공식 참고 자료

- [CPU PyTorch 설치](https://pytorch.org/get-started/locally/)
- [python-mecab-ko 설치](https://python-mecab-ko.readthedocs.io/en/latest/install/)
- [pygame mixer](https://www.pygame.org/docs/ref/mixer.html)
- [Raspberry Pi 카메라 소프트웨어](https://www.raspberrypi.com/documentation/computers/camera_software.html)
