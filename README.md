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
ollama pull qwen2.5:1.5b    # 초고속 대응 지침 생성 모델 (추천)
ollama pull bge-m3          # 고성능 임베딩 모델

# 3. 추가 시스템 의존성
# - Windows: HWP 파싱을 위해 olefile 패키지 사용 (전용 한글 프로그램 없이 동작)
# - Linux: sudo apt install libportaudio2 (PyAudio 용)

# 4. 데이터 동기화 (신규 매뉴얼 추가 시)
python -m rag.pipeline

# 5. 실행 (통합 최적화 버전)
python main.py
```

---

## 📂 프로젝트 구조

```text
-RAG-AI-/
├── config.py                    # 전역 설정 (센서 임계값, 모델, 최적화 옵션)
├── main.py                      # [MAIN] 통합 실행 진입점 (STT + RAG + Sensor)
│
├── sensors/                     # 센서 모듈 (재황)
│   ├── smoke.py                 #   MQ-2 연기 감지
│   ├── gas.py                   #   MQ-135 가스 감지
│   ├── temperature.py           #   DHT22 온도/습도
│   └── fusion.py                #   멀티센서 퓨전 & 위험도 산정
│
├── vision/                      # Vision AI (규태)
│   ├── camera.py                #   카메라 캡처
│   └── fire_detector.py         #   화재/연기 영상 판별 AI
│
├── rag/                         # RAG 엔진 (승훈+종화)
│   ├── pipeline.py              #   [CORE] 데이터 동기화 및 전체 파이프라인 관리
│   ├── parser.py                #   문서 파싱 (PDF, HWP, TXT) 및 Poison Pill 필터 (무결성 확보)
│   ├── chunker.py               #   시맨틱 분할 및 LaTeX 기호 원천 차단 엔진
│   ├── loader.py                #   가공된 JSON 데이터 로딩
│   ├── retriever.py             #   ChromaDB 기반 벡터 검색
│   └── chain.py                 #   QA 체인 및 프롬프트 최적화
│
├── voice/                       # 음성 모듈 (종화)
│   ├── stt.py                   #   실시간 음성 인식 (OpenAI Whisper)
│   ├── stt_vad.py               #   VAD 기반 정밀 음성 감지
│   ├── tts.py                   #   음성 안내 출력 제어
│   └── melo_wrapper.py          #   고성능 오프라인 MeloTTS 엔진 연동
│
├── gui/                         # GUI 모듈 (승훈)
│   └── dashboard.py             #   관제 대시보드
│
├── data/                        # 데이터 저장소
│   ├── raw_documents/           #   원본 매뉴얼 보관 (PDF, HWP, TXT)
│   ├── chunked_manuals.json     #   최종 정제된 지식 베이스 데이터
│   ├── preview_chunks.md        #   [Auto] 100% 평문화된 지식 베이스 미리보기
│   └── pipeline_state.json      #   증분 동기화 상태 기록 파일
│
├── alerts/                      # 경보 모듈 (재황)
│   ├── alarm.py                 #   부저/LED 경보 출력
│   └── notifier.py              #   관제실 알림 전송
│
└── PROJECT_PROPOSAL.md          # 프로젝트 최종 계획서
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
