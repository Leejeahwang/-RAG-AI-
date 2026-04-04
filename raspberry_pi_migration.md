# 🍓 라즈베리파이(Raspberry Pi) 이식 가이드

지금까지 구축하신 '엣지 세이버(Edge Saver)'는 라즈베리파이 같은 엣지 디바이스에서 작동하도록 설계되었습니다. 현재 맥(Mac)에서 작동하는 이 프로젝트를 라즈베리파이로 완벽하게 이식하기 위한 단계별 가이드입니다.

## 1. 필수 시스템 환경 (OS)
> [!IMPORTANT]
> **반드시 64-bit OS를 설치해야 합니다.** 
> Ollama 자체와 음성 인식 모델(faster-whisper) 등 최신 AI 패키지는 32-bit를 지원하지 않습니다. 
> * 추천 OS: **Raspberry Pi OS (64-bit)** (Bookworm 버전 권장) 또는 **Ubuntu 24.04 (64-bit)**

## 2. 코드 다운로드 (Git Clone)
라즈베리파이 터미널을 열고 지금 깃허브에 올리신(Push) 최신 코드를 다운로드합니다.
```bash
cd ~
git clone https://github.com/Leejeahwang/-RAG-AI-.git
cd ./-RAG-AI-
```

## 3. 시스템 의존성 및 패키지 설치
라즈베리파이는 macOS나 Windows와 달리 특정 하드웨어(오디오, GPIO) 접근을 위한 시스템 패키지를 OS 단에서 먼저 설치해 주어야 합니다.

### A. 오디오 및 필수 라이브러리 설치
음성 인식(STT/마이크)과 음성 출력(TTS/스피커)을 원활하게 쓰기 위해 설치합니다.
```bash
sudo apt update
sudo apt install -y python3-pyaudio portaudio19-dev python3-rpi.gpio flac espeak ffmpeg libespeak1 swig python3-dev
```

### B. 파이썬 가상환경 및 패키지 설치
라즈베리파이 OS (Bookworm 이상)에서는 가상환경 사용이 강제됩니다.
```bash
# 가상환경 생성 및 접속
python3 -m venv venv
source venv/bin/activate

# 깃허브에서 가져온 requirement.txt 설치
pip install -r requirements.txt

# (선택) 라즈베리파이용 하드웨어 제어 라이브러리 추가 설치
pip install RPi.GPIO
```
> [!TIP]
> 현재 맥에서 `⚠️ [경고] RPi.GPIO 라이브러리가 없습니다. (시뮬레이션 모드로 작동합니다)` 라는 메시지가 뜨지만, 라즈베리파이에서는 이 라이브러리가 정상적으로 깔리면서 **진짜 센서 모드**로 작동하게 됩니다!

## 4. 로컬 AI 모델 (Ollama) 설치 및 구동
라즈베리파이의 ARM 아키텍처에 맞게 Ollama를 설치하고 1.5B 모델을 올립니다.
*(주의: 라즈베리파이 5 8GB 모델을 적극 권장합니다. 메모리가 작으면 매우 느릴 수 있습니다.)*

```bash
# Ollama 설치
curl -fsSL https://ollama.com/install.sh | sh

# Ollama 백그라운드 서버 실행 (이미 실행 중일 수 있음)
# 모델 다운로드 및 실행
ollama run qwen2.5:1.5b
```
다운로드가 끝나고 프롬프트가 뜨면 `/bye`를 입력해 빠져나오세요. 이제 백그라운드에 1.5B 모델이 항시 대기 중 상태가 됩니다!

## 5. 하드웨어 설정 변경 (config.py)
이제 파일 코드를 라즈베리파이 실제 선 연결(핀 번호)에 맞게 살짝 수정해야 합니다.

* **GPIO 세팅:** `config.py`를 열고, 부저(Buzzer)나 LED가 연결된 실제 PIN 번동이 맞는지 확인합니다.
  ```python
  ALERT_BUZZER_PIN = 18
  ALERT_LED_PIN = 23
  ```
* **마이크 및 스피커:** USB 마이크나 3.5mm 스피커를 꽂은 뒤 음성 인식이 잘 안 된다고 느껴지면 터미널에서 `alsamixer`를 쳐서 마이크 볼륨이 꺼져있지 않은지 확인합니다.

---

## 🚀 6. 최종 실행
모든 준비가 끝났습니다! 가상환경(`(venv)`)이 켜진 상태에서 메인 파이프라인을 기동합니다.

```bash
python main.py
```
이제 라즈베리파이가 센서 값을 읽어오고 열을 감지하며, 엣지 상에서 AI가 비상 상황을 판단해 안내방송을 송출하게 될 것입니다!

---

## 🛠️ 7. 흔하게 발생하는 에러 해결 (Troubleshooting)

### Q1. `RuntimeError: Cannot determine SOC peripheral base address` 에러가 뜹니다.
라즈베리파이 5(또는 최신 Bookworm OS)에서 구형 `RPi.GPIO` 라이브러리가 새 칩셋을 인식하지 못해 발생합니다. 코드를 수정할 필요 없이, 최신 호환 패키지인 `rpi-lgpio`로 교체해 주면 깔끔하게 해결됩니다.
```bash
# 가상환경이 켜진 상태에서 터미널에 입력
pip uninstall -y RPi.GPIO
pip install rpi-lgpio
```

### Q2. 한글 글씨가 네모 박스(□□□)나 이상한 특수문자로 다 깨져서 나옵니다.
라즈베리파이 OS는 기본적으로 영문 환경이라 한글 폰트가 빠져있어서 생기는 시각적인 현상입니다. 한글 폰트를 시스템에 설치하고 껐다 켜주시면 바로 예쁜 한글이 나옵니다.
```bash
sudo apt update
sudo apt install -y fonts-nanum fonts-unfonts-core
```
