# 🔥 엣지 세이버 (Edge Saver)

> 멀티센서 + 카메라 AI + LLM/RAG를 결합한 **라즈베리파이 기반 지능형 화재 감시 시스템**

---

## 🚀 프로젝트 소개

기존 화재경보기의 높은 오경보율, 단순 ON/OFF 알림 한계를 극복하는 **엣지 AI 화재 감시 시스템**입니다. 연기·가스·온도 센서와 카메라 AI를 결합하여 화재를 정확히 판별하고, LLM+RAG가 건물 매뉴얼을 검색하여 **맞춤형 대응 지침을 자연어로 즉시 생성**합니다.

**핵심 차별점:**
- 🎯 **AI 오경보 필터링:** 센서 반응 시 카메라 AI가 2차 검증 → 거짓 경보 대폭 감소
- 🧠 **건물 맞춤 자연어 안내:** RAG가 건물 DB를 검색, LLM이 "CO2 소화기 사용, 서쪽 계단으로 대피" 등 구체적 지침 생성
- 📡 **완전 오프라인:** 화재로 통신 인프라가 다운되어도 엣지 AI가 독립 동작
- 💰 **저비용 대량 배치:** 라즈베리파이 기반으로 기존 스마트 시스템 대비 1/10 비용

---

## 🛠️ 설치 및 실행

```bash
# 1. 필수 라이브러리 설치 (RAG, Vision, Voice)
pip install -r requirements.txt

# 2. 로컬 LLM 서버 (Ollama) 설치 및 모델 다운로드
# https://ollama.com 에서 설치 후 아래 명령 실행
ollama pull qwen2.5:1.5b  # LLM 및 임베딩용 (config.py 설정)

# 3. 추가 시스템 의존성 (필요 시)
# - Windows: HWP 파싱을 위해 한글(HWP) 설치 필요
# - Linux: sudo apt install libportaudio2 (PyAudio 용)
# - Linux: sudo apt install espeak-ng (TTS 용)

# 4. 실행
python main.py
```

---

## 📂 프로젝트 구조

```text
-RAG-AI-/
├── config.py                    # 전역 설정 (센서 임계값, 모델, 위험도 기준)
├── main.py                      # 메인 진입점 (전체 파이프라인)
│
├── sensors/                     # 센서 모듈 (재황)
│   ├── smoke.py                 #   MQ-2 연기 감지
│   ├── gas.py                   #   MQ-135 가스 감지
│   ├── temperature.py           #   DHT22 온도/습도
│   └── fusion.py                #   멀티센서 퓨전 & 위험도 산정 (규태+재황)
│
├── vision/                      # Vision AI (규태)
│   ├── camera.py                #   카메라 캡처 ✅
│   └── fire_detector.py         #   화재/연기 영상 판별 AI
│
├── rag/                         # RAG 엔진 (승훈+종화)
│   ├── loader.py                #   문서 로딩 & 청킹 (승훈)
│   ├── retriever.py             #   벡터DB & 검색 (승훈)
│   ├── chain.py                 #   QA 체인 & 프롬프트 (승훈)
│   └── pdf_parser.py            #   PDF 파싱 (종화)
│
├── alerts/                      # 경보 모듈 (재황)
│   ├── alarm.py                 #   부저/LED 경보 출력
│   └── notifier.py              #   관제실 알림 전송
│
├── voice/                       # 음성 모듈 (종화)
│   └── tts.py                   #   오프라인 TTS 안내
│
├── gui/                         # GUI 모듈 (승훈)
│   └── dashboard.py             #   관제 대시보드
│
├── docker/                      # Docker 설정 (재황)
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── data/                        # 매뉴얼 데이터 (종화가 수집/파싱)
├── _archive/                    # 이전 버전 코드 보관
└── PROJECT_PROPOSAL.md          # 프로젝트 최종 계획서
```

---

## 👥 팀원

| 이름 | 역할 | 담당 모듈 |
|------|------|-----------|
| 이재황 | PM & DevOps | `sensors/`, `alerts/`, `docker/`, RPi |
| 박규태 | Vision AI | `vision/`, `sensors/fusion.py` |
| 이승훈 | GUI & RAG Search | `gui/`, `rag/` |
| 채종화 | Voice & Data | `voice/`, `rag/pdf_parser.py`, `data/` |
