# 📋 엣지 세이버 — 구현 현황 & 담당자

> 마지막 업데이트: 2026-03-25

---

## 🗂️ 프로젝트 구조 & 구현 상태

```
-RAG-AI-/
├── config.py                    ✅ 구현됨    (전체)
├── main.py                      ✅ 구현됨    (전체)
│
├── sensors/                     👤 재황 (+규태: fusion)
│   ├── smoke.py                 ✅ 구현됨 (시뮬레이션)
│   ├── gas.py                   ✅ 구현됨 (시뮬레이션)
│   ├── temperature.py           ✅ 구현됨 (시뮬레이션)
│   └── fusion.py                ✅ 구현됨 (위험도 산정)
│
├── vision/                      👤 규태
│   ├── camera.py                ✅ 구현됨 (OpenCV 캡처)
│   └── fire_detector.py         📌 TODO (화재 영상 판별 AI)
│
├── rag/                         👤 승훈(검색) + 종화(파싱)
│   ├── loader.py                ✅ 구현됨
│   ├── retriever.py             ✅ 구현됨
│   ├── chain.py                 ✅ 구현됨
│   └── pdf_parser.py            📌 TODO
│
├── alerts/                      👤 재황
│   ├── alarm.py                 ✅ 구현됨 (시뮬레이션)
│   └── notifier.py              ✅ 구현됨 (시뮬레이션)
│
├── voice/                       👤 종화
│   └── tts.py                   📌 TODO
│
├── gui/                         👤 승훈
│   └── dashboard.py             📌 TODO
│
├── docker/                      👤 재황
│   ├── docker-compose.yml       📌 TODO
│   └── Dockerfile               📌 TODO
│
├── data/                        📂 매뉴얼 데이터 (종화가 PDF 파싱 후 저장)
├── _archive/                    🗂️ 보관용 (이전 버전 코드)
├── PROJECT_PROPOSAL.md          ✅ 완료
├── PROJECT_STATUS.md            ✅ 완료
├── .gitignore
└── README.md                    ✅ 완료
```

---

## 👥 팀원별 할 일 요약

### 👤 이재황 — PM & DevOps (`sensors/`, `alerts/`, `docker/`)

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `sensors/smoke.py` | ✅ 시뮬레이션 | Phase 3: MQ-2 GPIO 연동 |
| `sensors/gas.py` | ✅ 시뮬레이션 | Phase 3: MQ-135 GPIO 연동 |
| `sensors/temperature.py` | ✅ 시뮬레이션 | Phase 3: DHT22 GPIO 연동 |
| `alerts/alarm.py` | ✅ 시뮬레이션 | Phase 3: 부저/LED GPIO 제어 |
| `alerts/notifier.py` | ✅ 시뮬레이션 | Phase 2: MQTT 관제실 전송 |
| `docker/` | 📌 TODO | Docker Compose 멀티 서비스 구성 |
| 라즈베리파이 | 📌 TODO | RPi 환경 구축, systemd 자동 실행 |

### 👤 박규태 — Vision AI (`vision/`, `sensors/fusion.py`)

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `vision/camera.py` | ✅ 완료 | OpenCV 웹캠 캡처 구현됨 |
| `vision/fire_detector.py` | 📌 TODO | 화재/연기 영상 판별 AI (YOLOv8 또는 HSV 필터링) |
| `sensors/fusion.py` | ✅ 구현됨 | 멀티센서 퓨전 위험도 산정 (추후 고도화) |

### 👤 이승훈 — GUI & RAG Search (`gui/`, `rag/`)

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `rag/loader.py` | ✅ 완료 | 문서 로딩 & 청킹 |
| `rag/retriever.py` | ✅ 완료 | 벡터DB 생성 & 검색 |
| `rag/chain.py` | ✅ 완료 | QA 체인 & 화재 대응 프롬프트 |
| `gui/dashboard.py` | 📌 TODO | 관제 대시보드 (센서 현황 + 경보 + 챗봇) |

### 👤 채종화 — Voice & Data (`voice/`, `rag/pdf_parser.py`)

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `rag/pdf_parser.py` | 📌 TODO | 소방 매뉴얼 PDF 수집 및 파싱 (PyMuPDF) |
| `voice/tts.py` | 📌 TODO | 오프라인 TTS 음성 안내 (pyttsx3) |

---

## 📊 전체 진행률

| 구분 | 완료 | 남음 | 진행률 |
|------|------|------|--------|
| 공통 (config, main) | 2 | 0 | ██████████ 100% |
| 센서/알림 (재황) | 5 | 3 | ██████░░░░ 63% |
| Vision (규태) | 2 | 1 | ███████░░░ 67% |
| RAG/GUI (승훈) | 3 | 1 | ███████░░░ 75% |
| Voice/PDF (종화) | 0 | 2 | ░░░░░░░░░░ 0% |
| **전체** | **12** | **7** | **██████░░░░ 63%** |

---

> 구현 완료 시 해당 항목의 📌 를 ✅ 로 변경하고, 날짜를 업데이트해 주세요.
