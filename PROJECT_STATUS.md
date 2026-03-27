# 📋 엣지 세이버 — 구현 현황 & 담당자

> 마지막 업데이트: 2026-03-28

---

## 🖥️ Phase 1~2: PC에서 할 일 (현재 단계)

### 👤 박규태 — Vision AI

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `vision/camera.py` | ✅ 완료 | OpenCV 웹캠 캡처 |
| `vision/fire_detector.py` | ✅ 완료 | 화재/연기 영상 판별 AI (로컬 YOLOv8 + Roboflow 하이브리드) |
| `sensors/fusion.py` | 📌 TODO | 위험도 등급 산정 로직 설계 |

### 👤 이승훈 — GUI & RAG

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `rag/loader.py` | ✅ 완료 | 문서 로딩 & 청킹 |
| `rag/retriever.py` | ✅ 완료 | 벡터DB 생성 & 검색 |
| `rag/chain.py` | ✅ 완료 | QA 체인 & 화재 대응 프롬프트 |
| `gui/dashboard.py` | 📌 TODO | 관제 대시보드 (Streamlit/PyQt) |

### 👤 채종화 — Voice & Data

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `rag/pdf_parser.py` | 📌 TODO | 소방 매뉴얼 PDF 수집 및 파싱 |
| `voice/tts.py` | 📌 TODO | 오프라인 TTS 음성 안내 (pyttsx3) |

### 👤 이재황 — 통합 테스트 & 인프라

| 파일 | 상태 | 할 일 |
|------|------|-------|
| `docker/` | 📌 TODO | Docker Compose 환경 구성 |
| 통합 테스트 | 📌 TODO | 전체 파이프라인 E2E 시나리오 테스트 |
| `main.py` 고도화 | 📌 TODO | 센서→Vision→RAG→알림 통합 루프 완성 |

---

## 🔧 Phase 3: 라즈베리파이에서 할 일 (추후 4명 재분배)

> ⚠️ 아래 작업들은 RPi 하드웨어가 준비된 후 4명이 다시 분배합니다.

| 파일 | 할 일 |
|------|-------|
| `sensors/smoke.py` | MQ-2 연기 감지 GPIO 연동 |
| `sensors/gas.py` | MQ-135 가스 감지 GPIO 연동 |
| `sensors/temperature.py` | DHT22 온도/습도 GPIO 연동 |
| `alerts/alarm.py` | 부저/LED GPIO 경보 출력 |
| `alerts/notifier.py` | MQTT 관제실 실시간 전송 |
| `vision/camera.py` | CSI 카메라 모듈 연동 (현재 USB 웹캠용) |
| RPi 환경 구축 | Ollama + Docker 설치, systemd 자동 실행 |
| 성능 최적화 | 모델 양자화, 추론 속도 튜닝 |

---

## 📊 Phase 1~2 진행률 (PC 작업 기준)

| 구분 | 완료 | 남음 | 진행률 |
|------|------|------|--------|
| Vision (규태) | 2 | 1 | ██████░░░░ 66% |
| RAG/GUI (승훈) | 3 | 1 | ███████░░░ 75% |
| Voice/PDF (종화) | 0 | 2 | ░░░░░░░░░░ 0% |
| 인프라 (재황) | 0 | 3 | ░░░░░░░░░░ 0% |
| **전체** | **5** | **7** | **████░░░░░░ 41%** |

---

> 구현 완료 시 해당 항목의 📌 를 ✅ 로 변경하고, 날짜를 업데이트해 주세요.
