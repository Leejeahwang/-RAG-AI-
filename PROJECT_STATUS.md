# 📋 엣지 세이버 — 구현 현황 & 담당자

> 마지막 업데이트: 2026-03-24

---

## 🗂️ 프로젝트 구조 & 구현 상태

```
-RAG-AI-/
├── config.py                    ✅ 구현됨    (전체)
├── main.py                      ✅ 구현됨    (전체)
├── test.py                      ✅ 구현됨    (전체)
│
├── rag/                         👤 승훈
│   ├── loader.py                ✅ 구현됨
│   ├── retriever.py             ✅ 구현됨
│   ├── chain.py                 ✅ 구현됨
│   └── pdf_parser.py            📌 TODO
│
├── vision/                      👤 규태
│   └── camera.py                📌 TODO
│
├── voice/                       👤 종화
│   ├── stt.py                   📌 TODO
│   └── tts.py                   📌 TODO
│
├── gui/                         👤 종화
│   └── app.py                   📌 TODO
│
├── docker/                      👤 재황
│   ├── docker-compose.yml       📌 TODO
│   └── Dockerfile               📌 TODO
│
├── _archive/                    🗂️ 보관용
├── edge_saver_manual.txt        ✅ 완료
├── implementation_plan.md       ✅ 완료
└── README.md                    ✅ 완료
```

---

## 👥 팀원별 할 일 요약

### 👤 이승훈 — RAG Backend (`rag/`)

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `rag/loader.py` | ✅ 완료 | 문서 로딩 & 청킹 |
| `rag/retriever.py` | ✅ 완료 | 벡터DB 생성 & 검색 |
| `rag/chain.py` | ✅ 완료 | QA 체인 & 프롬프트 |
| `rag/pdf_parser.py` | 📌 TODO | 적십자 매뉴얼 PDF 파싱 (PyMuPDF), 스마트 청킹 (300~500자) |

### 👤 박규태 — Vision AI (`vision/`)

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `vision/camera.py` | 📌 TODO | OpenCV 웹캠 캡처, 프레임 선택 전략, 이미지 전처리, Vision→RAG 연결 |

### 👤 채종화 — Voice & GUI (`voice/`, `gui/`)

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `voice/stt.py` | 📌 TODO | 오프라인 STT (vosk 한국어 모델), 웨이크워드("세이버") 감지 |
| `voice/tts.py` | 📌 TODO | 오프라인 TTS (pyttsx3), 한국어 음성 출력 |
| `gui/app.py` | 📌 TODO | 터치스크린용 GUI (Streamlit 또는 PyQt) |

### 👤 이재황 — DevOps & HW (`docker/`)

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `docker/docker-compose.yml` | 📌 TODO | Ollama + App 멀티 서비스 구성 |
| `docker/Dockerfile` | 📌 TODO | 컨테이너 이미지 빌드 설정 |
| 라즈베리파이 세팅 | 📌 TODO | RPi 환경 구축, systemd 자동 실행, 성능 최적화 |

---

## 📊 전체 진행률

| 구분 | 완료 | 남음 | 진행률 |
|------|------|------|--------|
| 공통 (config, main, test) | 3 | 0 | ██████████ 100% |
| RAG (승훈) | 3 | 1 | ███████░░░ 75% |
| Vision (규태) | 0 | 1 | ░░░░░░░░░░ 0% |
| Voice (종화) | 0 | 2 | ░░░░░░░░░░ 0% |
| GUI (종화) | 0 | 1 | ░░░░░░░░░░ 0% |
| Docker (재황) | 0 | 2 | ░░░░░░░░░░ 0% |
| **전체** | **6** | **7** | **████░░░░░░ 46%** |

---

> 구현 완료 시 해당 항목의 📌 를 ✅ 로 변경하고, 날짜를 업데이트해 주세요.
