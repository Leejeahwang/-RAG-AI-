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
   git clone -b rpi https://github.com/Leejeahwang/-RAG-AI-.git
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

---

## 📷 5. 라즈베리파이 카메라 모듈 3 (Camera Module 3) 확인 & 연동 가이드

라즈베리파이 5 및 최신 OS(Bookworm) 환경에서 카메라마이크 3(CSI 포트 연결 방식, IMX708 센서)을 사용할 때는 libcamera 스택을 사용해야 하므로, 기존 USB 웹캠 방식과 다르게 인식 검증이 필요합니다.

### 1) 시스템 레벨 하드웨어 인식 확인
터미널에서 아래 명령을 실행하여 카메라 보드가 하드웨어적으로 올바르게 결착되어 드라이버가 로드되었는지 확인합니다:

```bash
rpicam-hello --list-cameras
```
또는
```bash
libcamera-hello --list-cameras
```

* **정상 작동 시 출력 예시**:
  ```text
  Available cameras
  -----------------
  0 : imx708 [4608x2592] (/base/soc/pcie@120000/rp1/i2c@80000/imx708@1a)
  ```
  *(만약 `No cameras available` 메시지가 뜬다면 메인보드 슬롯 케이블 방향 및 체결 상태를 다시 검검해야 합니다.)*

### 2) Python (OpenCV)에서 모듈 3 연결 상태 검증 코드
라즈베리파이 5의 libcamera 환경에서 OpenCV가 정상적으로 프레임을 캡처할 수 있는지 체크하는 독립 실행용 파이썬 스크립트(`check_camera.py`)입니다.

```python
# check_camera.py
import cv2
import sys

def test_rpi_camera():
    print("🔍 라즈베리파이 카메라 모듈 3 인식 테스트 시작...")
    
    # VideoCapture 생성 (라즈베리파이 V4L2 호환 백엔드 사용)
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    
    if not cap.isOpened():
        print("❌ 카메라 장치를 열 수 없습니다! (/dev/video0 노드 부재)")
        print("💡 팁: 'libcamerify python3 check_camera.py' 로 실행해 보십시오.")
        sys.exit(1)
        
    # 해상도 지정
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    # 테스트 프레임 캡처
    ret, frame = cap.read()
    if ret:
        print("✅ RPi 카메라 모듈 3로부터 프레임 수집 성공!")
        print(f"   - 해상도: {frame.shape[1]}x{frame.shape[0]}")
        cv2.imwrite("rpi_cam3_test.jpg", frame)
        print("💾 테스트 샷이 'rpi_cam3_test.jpg'로 저장되었습니다.")
    else:
        print("❌ 카메라 장치는 열렸으나, 비디오 프레임을 획득하지 못했습니다.")
        
    cap.release()

if __name__ == "__main__":
    test_rpi_camera()
```

### 3) 💡 최상의 작동 팁: `libcamerify` 도구 사용
라즈베리파이 5에서 OpenCV 코드(`cv2.VideoCapture(0)`)가 드라이버 제약으로 카메라를 열지 못할 경우, 라즈베리파이 OS가 자체 지원하는 **libcamerify** 래퍼를 씌워 파이썬을 실행하면 기존 코드를 하나도 고치지 않고 완벽하게 에뮬레이션 작동합니다.

```bash
# 가상환경이 활성화된 상태에서 실행
libcamerify python3 main.py
```

---

## 🔤 6. 터미널 한글 깨짐 (네모 상자 ㅁㅁㅁ 표시) 해결 방법

라즈베리파이 OS를 초기화한 직후에는 한글 폰트나 한국어 로케일이 설치되어 있지 않아 터미널 출력문이 깨지거나 사각형(ㅁㅁㅁ)으로 보일 수 있습니다. 아래 명령어로 한글 글꼴 및 한글 인코딩 설정을 복구하십시오.

### 1) 한글 나눔 폰트 설치 (네모 박스 해결)
터미널에서 한글을 그래픽으로 예쁘게 렌더링하기 위해 다음 시스템 폰트 패키지를 설치합니다:
```bash
sudo apt install -y fonts-nanum fonts-unfonts-core
```

### 2) 시스템 한글 로케일(Locale) 인코딩 생성
한글 UTF-8 인코딩을 생성하여 시스템에 등록합니다:
```bash
sudo locale-gen ko_KR.UTF-8
sudo update-locale LANG=ko_KR.UTF-8
```

### 3) 수동 로케일 구성 재확인 (필요시)
만약 계속 영어나 깨진 폰트로 보인다면 아래 명령을 실행하여 설정 메뉴를 엽니다:
```bash
sudo dpkg-reconfigure locales
```
- 스페이스 바를 눌러 **`ko_KR.UTF-8 UTF-8`** 항목을 체크(별표 `*` 표시)하고 엔터를 칩니다.
- 기본 로케일(default locale) 선택 단계에서도 **`ko_KR.UTF-8`** 을 지정하고 엔터를 눌러 완료합니다.
- 설정을 마친 후 터미널 창을 닫았다가 다시 열면 한글이 정상적으로 출력됩니다.

