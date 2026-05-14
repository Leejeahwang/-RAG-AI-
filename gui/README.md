🖥️ Edge Saver 통합 관제 대시보드 (Dashboard)

본 모듈은 Edge Saver 프로젝트의 프론트엔드이자 통합 제어 시스템으로, 라즈베리파이 5 환경에서 실시간 데이터 시각화 및 지능형 AI 대응을 총괄하는 지능형 관제 플랫폼입니다. 센서 데이터와 비전 분석을 결합한 위험 판단 및 RAG(검색 증강 생성) 기반의 음성 가이드를 실시간으로 제공합니다.

## 📁 파일 구성

| 파일 | 용도 | 실행 환경 |
|---|---|---|
| `dashboard.py` | 프로덕션 대시보드 (실제 LLM + STT + TTS + 센서 + 카메라) | 라즈베리파이 5 (모든 하드웨어 연결) |
| `dashboardtest.py` | 라즈베리파이 없이 PC에서 검증용 — 실제 LLM은 사용하되 STT/TTS/센서/카메라는 가짜 | 일반 PC (Ollama만 있으면 됨) |
| `components.py` | 패널/위젯 렌더링 함수 모음 (`render_*`) | — |
| `workers.py` | 백그라운드 스레드 (센서/화재/STT/LLM/MQTT/디스패처) | — |
| `state.py` | `RUNTIME` 싱글톤 + 스냅샷 데이터클래스 | — |

`dashboard.py`와 `dashboardtest.py`는 **동일한 UI 컴포넌트(`components.py`)와 LLM 워커 경로(`workers.py`)를 공유**합니다. 차이는 워커가 받는 의존성(`qa`, `tts`, `stt`)이 실제냐 가짜냐 뿐입니다.

## 🚀 실행 방법

### A. 단독 노드 모드 (라즈베리파이 1대 + 모니터 직결)

라즈베리파이가 모든 것을 직접 처리 — 센서 읽기, 카메라 분석, LLM 추론, 화면 표시.

```bash
# 라즈베리파이에서
streamlit run gui/dashboard.py
```

`MQTT_MODE` 환경변수 없음(기본 0). 본인 구역만 단일 화면으로 표시.

### B. 관제 PC ↔ 라즈베리파이 다중구역 모드

여러 라즈베리파이가 센서/카메라 데이터를 MQTT로 발행하고, 관제 PC가 한 대시보드에서 통합 감시.

**B-1. 관제 PC에서 (대시보드 + LLM):**
```powershell
# 가상환경 활성화
.\.venv\Scripts\Activate.ps1

# Ollama 모델 설치 (한 번만)
ollama pull qwen2.5:1.5b

# MQTT 브로커 실행 중인지 확인 (별도 터미널에서 mosquitto 등 실행 필요)
# 그 후 관제 모드로 대시보드 실행
$env:MQTT_MODE=1; streamlit run gui/dashboard.py
```

**B-2. 각 라즈베리파이에서 (센서/카메라 데이터 발행):**
```bash
# Pi에서 — ZONE은 구역 이름, BROKER_HOST는 관제 PC의 IP
BROKER_HOST=192.168.0.100 ZONE=A구역 python rpi_publisher.py
```

여러 대를 띄울 때는 각 Pi마다 `ZONE`만 다르게 설정 (`A구역`, `B구역`, `C구역`…).
`rpi_publisher.py`는 [프로젝트 루트](../rpi_publisher.py)에 있습니다. 1초 주기로 센서, 2초 주기로 화재 탐지 결과를 MQTT로 발행합니다.

발행 토픽:
- `factory/sensors/{ZONE}` — 온도/가스/연기/습도
- `factory/fire/{ZONE}` — 화재 탐지 결과 (detected/confidence)

### C. 테스트 모드 (라즈베리파이 없이 PC 단독)

라즈베리파이도 MQTT 브로커도 필요 없음. PC에서 모든 것을 시뮬레이션.

```powershell
# 가상환경 활성화
.\.venv\Scripts\Activate.ps1

# Ollama 모델 설치 (한 번만)
ollama pull qwen2.5:1.5b

# 테스트 대시보드 실행
streamlit run gui/dashboardtest.py
```

A/B/C 3구역 시나리오가 180초 슬롯으로 자동 순회하며, 실제 LLM은 그대로 작동.

### 사용 모드 비교

| 모드 | 진입점 | MQTT_MODE | 하드웨어 | rpi_publisher.py |
|---|---|---|---|---|
| A. 단독 노드 | `gui/dashboard.py` | 0 (기본) | Pi 1대 (모니터 직결) | 불필요 |
| B. 다중구역 관제 | `gui/dashboard.py` + `rpi_publisher.py` | 1 | 관제 PC + Pi N대 | 각 Pi마다 1개 실행 |
| C. PC 테스트 | `gui/dashboardtest.py` | (강제 1) | PC만 | 불필요 |

## 📐 인터페이스 레이아웃

좌측 메인(1.4) : 우측 데이터(1) 비율의 분할 레이아웃.

### 상단 (공통)
- **헤더:** 시스템 타이틀 + 다크/라이트 테마 토글
- **비상 배너:** 위험도 LV4 이상일 때 자동 노출
- **상태 바:** LIVE / SENSORS / AI READY 표시

### 좌측 메인 패널
- **CCTV Stream:** 실시간 영상 + YOLOv8 화재 탐지 결과 시각화 (test 모드는 합성 프레임)
- **🎙️ 음성 브리핑 토글:** 마이크 STT 활성화/비활성화
  - `dashboard.py` → 실제 Whisper STT + PyAudio 스트림
  - `dashboardtest.py` → FakeSTT (토글 ON → 2초 뒤 랜덤 가짜 질문 자동 입력 → 토글 자동 OFF)
- **⌨️ 텍스트 질의 (expander):** 마이크가 없거나 정확한 질문을 보내고 싶을 때 사용
  - 입력 → `AI 질의 전송` 버튼 → LLM 큐로 즉시 라우팅
  - 두 파일 모두에서 동일하게 동작

### 우측 데이터 패널
- **Sensor Metrics:** 온도(°C) / 가스(ppm) / 연기 / 습도(%) 메트릭
- **Risk Gauge:** `fusion.calculate_risk_level()` 결과(LV1~5)를 색상 변화 게이지로 표시
- **AI Command Center:** RAG가 생성한 대응 지침을 항상 노출. 생성 중에는 분석 인디케이터 표시
- **Tactical Feed:** 시스템 로그를 타임스탬프 역순으로 표시

## 🗺️ 레이아웃 모드 (MQTT_MODE)

환경변수 `MQTT_MODE`에 따라 화면 구성이 갈립니다.

### `MQTT_MODE=1` — 다중구역 관제 모드
- 한 대시보드가 여러 라즈베리파이(A/B/C…) 구역을 동시에 감시
- **첫 화면:** 구역 카드 그리드 (`render_zone_overview`) — 각 카드에 온라인 여부 / 위험도 / 센서 요약 / `상세보기` 버튼
- **카드 클릭** → 그 구역만 상세 화면 (`render_zone_nav` 상단 네비 + 카메라 + 데이터 패널)
- `alert_dispatcher` 워커가 모든 구역의 위험도를 폴링하여 임계치 초과 시 자동 LLM 트리거

### `MQTT_MODE=0` — 단일구역 노드 모드
- 라즈베리파이 1대에 모니터 직결, 본인 구역만 표시
- 구역 선택 단계 없이 바로 카메라 + 데이터 패널
- `dashboard.py`에서만 사용 가능 (`dashboardtest.py`는 항상 `MQTT_MODE=1`로 강제)

## 🚨 핵심 전술 로직

### 1. 비동기 멀티스레딩 아키텍처
모든 백그라운드 작업이 독립 스레드로 운영되어 무중단 관제를 실현합니다.

| 워커 | 주기 | 역할 |
|---|---|---|
| `sensor_worker` / `mqtt_sensor_worker` | 1s | 센서값 수집 + 위험도 계산 |
| `fire_worker` / `mqtt_fire_worker` | 2s | CCTV 프레임 → YOLO 화재 탐지 |
| `stt_worker` / `fake_stt_worker` | 토글 기반 | 음성 → 텍스트 |
| `llm_worker` | 큐 기반 | `qa.invoke()` + TTS + 알림 발송 |
| `alert_dispatcher` | 1s | 모든 구역 위험도 폴링 → LLM 자동 트리거 |

**큐 기반 통신:** `PriorityQueue`로 비상 지침(우선순위 0)과 일반 질의(우선순위 1)를 분리하여 자원 충돌 방지.

### 2. 다국어 지능형 음성 인터페이스
`detect_lang()` 정규표현식 기반 언어 감지로 한국어/일본어/영어/중국어를 자동 구분, 사용자 언어에 맞춰 TTS 출력.

### 3. 선제적 대응 및 세이프 가드
- **Emergency Auto-Pilot:** 위험도 LV4 이상 또는 화재 감지 시, `alert_dispatcher`가 사용자 시야와 무관하게 RAG 엔진을 가동하여 비상 피난 방송(TTS) + 외부 알림(Notifier) + GPIO 알람을 선제 실행
- **CAS 락:** `try_claim_alert()` / `try_claim_zone_alert()`으로 동일 비상에 대한 중복 트리거를 원자적으로 차단

## 🤖 LLM 통합

`dashboard.py`와 `dashboardtest.py` 모두 동일한 RAG 파이프라인을 사용합니다.

- **모델:** Ollama 로컬 LLM (기본 `qwen2.5:1.5b`, [config.py](../config.py)에서 변경)
- **벡터 스토어:** Chroma (`chroma_db/`)
- **매뉴얼 소스:** [data/](../data/) 폴더의 `factory_*_manual.txt`, `zone_*_layout.txt`
- **체인:** [rag/chain.py](../rag/chain.py) — `RetrievalQA` + 한국어 시스템 프롬프트

**test 모드 폴백:** `dashboardtest.py`는 Ollama 미실행 / 모델 미설치 / 벡터DB 누락 시 자동으로 `FakeQA`(하드코딩 응답)로 폴백하여 대시보드 자체는 항상 부팅됩니다. 로그 패널에서 `[REAL-QA]` 또는 `[QA] FakeQA`로 어느 모드인지 확인 가능합니다.

## 🧰 테스트 시나리오 (dashboardtest.py)

라즈베리파이 없이 PC에서 다음 흐름을 검증할 수 있습니다.

1. **구역 순회 시나리오:** A → B → C 각 구역이 180초 슬롯으로 자동 순회 (60초 상승 → 60초 화재 유지 → 60초 하강)
2. **자동 비상 트리거:** 화재 단계 진입 시 `alert_dispatcher`가 자동으로 RAG 비상 지침 생성
3. **수동 질의:** 텍스트 박스 또는 마이크 토글로 사용자 질문 전송
4. **AI 응답 품질:** 실제 LLM이 매뉴얼을 검색하고 답변 생성 — 모델을 더 큰 것으로 바꿀수록 품질 향상
