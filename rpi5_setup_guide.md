# 엣지 세이버 (Edge Saver) - 라즈베리파이 5 (Raspberry Pi 5) 이식 및 설치 가이드

본 가이드는 초기화된 라즈베리파이 5(Raspberry Pi 5) 보드에 본 RAG AI 화재 안전 대피 안내 시스템을 처음부터 설치하고 기동하는 전 과정을 안내합니다.

---

## 🛠️ 1. 하드웨어 및 OS 권장사항

- **보드**: Raspberry Pi 5 (RAM 8GB 권장 - 로컬 LLM 구동 목적)
- **OS**: **Raspberry Pi OS (64-bit) Bookworm** (Debian 12 기반)
- **주변 장치**: USB 카메라(비전 감지용), 오디오 스피커(TTS 대피 방송 출력용)

---

## 💾 2. 단계별 설치 및 설정 순서

### Step 1: 시스템 필수 패키지 설치
오픈CV GUI 충돌 방지, 마이크/오디오 드라이버 및 TTS(Espeak) 연동을 위해 다음 시스템 라이브러리를 터미널에서 반드시 먼저 설치해야 합니다.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-opencv libportaudio2 libopenblas-dev espeak git curl python3-pip python3-venv
```

### Step 2: 로컬 LLM 엔진 (Ollama) 설치 및 모델 다운로드
로컬 RAG 추론을 위해 Ollama를 설치하고 `qwen2.5:1.5b` 모델을 확보합니다.

1. **Ollama 설치**:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```
2. **Qwen 모델 다운로드 및 작동 확인**:
   ```bash
   ollama run qwen2.5:1.5b
   ```
   *(터미널 창에 대화 프롬프트가 뜨면 정상 설치된 것이며, `/bye`를 입력하여 나옵니다.)*

### Step 3: 프로젝트 복제 및 가상환경 구성
프로젝트 코드를 보드에 가져와 가상환경을 구축합니다.

1. **저장소 복제**:
   ```bash
   git clone <깃허브 저장소 URL>
   cd -RAG-AI--dev_park
   ```
2. **Python 가상환경 생성 및 활성화**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

### Step 4: 라즈베리파이 전용 Python 의존성 패키지 설치
제공되는 라즈베리파이 전용 `requirements_rpi.txt` 파일을 이용하여 종속 패키지를 설치합니다.

```bash
pip install --upgrade pip
pip install -r requirements_rpi.txt
```

> 💡 **FAISS-CPU 설치 에러 발생 시 대처법**:
> 라즈베리파이 ARM 아키텍처 환경에 따라 `faiss-cpu` pip 설치 시 컴파일 에러가 날 수 있습니다. 이 경우 아래와 같이 시스템 패키지로 직접 설치해 주십시오.
> ```bash
> # requirements_rpi.txt 내 faiss-cpu 줄을 지우거나 주석 처리한 후
> sudo apt install -y libfaiss-dev
> ```

---

## ⚙️ 3. 최적화 설정 확인 (`config.py`)

라즈베리파이 5 보드의 리소스 최적화 및 오동작 방지를 위해 [config.py](config.py) 파일이 아래와 같이 세팅되어 있는지 확인합니다.

* **`LLM_MODEL = "qwen2.5:1.5b"`**: 속도와 지시 준수 품질의 최적 밸런스를 위한 1.5B 모델 지정.
* **`STT_ENABLED = False`**: 라즈베리파이 기본 오디오 드라이버(ALSA)의 버퍼 오버플로우 및 세그멘테이션 오류 방지를 위해 비활성화 상태 유지 (텍스트 모드로 기동).
* **`TTS_ENGINE = "PYTTSX3"`**: 오프라인에서 딜레이 없이 한글을 음성 출력하기 위해 내장 espeak 드라이버 기반 SAPI 엔진 사용.
* **`TTS_RATE = 190`**: 차분하고 인지하기 쉬운 1.0배속 표준 말하기 속도.

---

## 🚀 4. 시스템 실행 및 동작 검증

1. **시스템 실행**:
   ```bash
   python3 main.py
   ```
2. **최초 실행 시 지식베이스(FAISS DB) 자동 재생성**:
   - 기존 빌드 폴더가 없을 경우, `data/raw_documents/*.txt` 파일(소화기구 매뉴얼, 공장 화재 대처법 등 10개 문서)을 탐색하여 **자동으로 FAISS 벡터 데이터베이스를 구축**합니다. (`faiss_db/` 생성됨)
3. **화재 감지 및 RAG 긴급 대피 지침 테스트**:
   - 카메라가 구동되며 화면 감시를 시작합니다.
   - 카메라에 불이나 연기 요소를 시뮬레이션(또는 가상 화재 트리거 작동)하면 센서 값이 위험 레벨 5(재난)로 자동 승격되어 사이렌과 함께 AI 긴급 피난 안내가 기동합니다.
   - AI가 규격화된 3대 항목(1. 종류/장소, 2. 대치방법/소방용품 위치, 3. 대피로)에 맞춰 대피 지침을 생성하고 스피커로 안내 낭독하는지 확인합니다.
