# EDGE SAVER 원격 관제 대시보드

라즈베리파이 5는 화면 없이 혼자 감시·경보·대피 방송을 합니다. 이 대시보드는 Pi가 MQTT로 보낸 결과를 노트북·관제 PC 브라우저에 **표시만** 합니다.

```
라즈베리파이 main.py ──MQTT(Pi의 mosquitto)──▶ 관제 PC  streamlit run gui/dashboard.py
   판단·경보·방송                                 표시 + 관제사 질의(자체 RAG)
```

- 판단은 Pi가 합니다. 대시보드는 위험도를 다시 계산하지 않고, 카메라·센서·경보를 직접 다루지 않습니다.
- 네트워크가 끊겨도 Pi는 혼자 방송을 계속합니다. 대시보드는 그 구역을 **신호 없음**으로 표시합니다.
- 관제사 질문은 관제 PC가 자체 RAG로 답합니다. RAG가 없어도 수신·표시는 동작합니다.

## 파일

| 파일 | 역할 | 실행 위치 |
|---|---|---|
| `dashboard.py` | Streamlit 진입점, 레이아웃 | 관제 PC |
| `components.py` | CSS와 화면 패널 | 관제 PC |
| `state.py` | 구역별 수신 상태 (thread-safe) | 관제 PC |
| `workers.py` | MQTT 수신, 관제사 질의 RAG·STT | 관제 PC |
| `protocol.py` | 메시지 형식 (만들기·읽기) | 양쪽 |
| `mqtt_settings.py` | 브로커 주소·토픽·주기 설정 | 양쪽 |
| `edge_publisher.py` | Pi 발행 모듈 (`main.py`가 호출) | Pi |
| `fake_edge.py` | PC 테스트용 가짜 Pi | 관제 PC |
| `PROTOCOL.md` | 메시지 형식 문서 | |
| `MAIN_INTEGRATION.md` | `main.py`에 넣을 발행 코드와 Pi 설정 | |
| `tests/` | 메시지 형식·수신·발행 테스트 | |

## 실행

### 관제 PC

```powershell
pip install -r gui/requirements_dashboard.txt
$env:MQTT_BROKER_HOST = "192.168.0.50"     # Pi의 IP
streamlit run gui/dashboard.py
```

`.env`에 `MQTT_BROKER_HOST=192.168.0.50`을 넣어도 됩니다. 관제사 질의(RAG·음성)까지 쓰려면 루트 `requirements.txt`와 RAG 인덱스도 준비하세요. 마이크를 쓰지 않으면 `.env`에 `STT_ENABLED=false`를 넣습니다.

### Pi

`main.py`에 발행 코드를 넣고 mosquitto를 설정합니다. 방법은 [MAIN_INTEGRATION.md](MAIN_INTEGRATION.md)에 있습니다.

### Pi 없이 PC에서 테스트

```powershell
mosquitto -v                                  # 창 1: 로컬 브로커 (mosquitto 설치 필요)
python -m gui.fake_edge --loop                # 창 2: 가짜 Pi A구역
python -m gui.fake_edge --zone B --speed 2    # 창 3: (선택) B구역
streamlit run gui/dashboard.py                # 창 4: 대시보드 (MQTT_BROKER_HOST 기본값 127.0.0.1)
```

가짜 Pi는 다음 순서로 상태를 보냅니다. 정상 → 사진 오탐 차단 → 조기 연기(LV2) → 화재(LV5, 고정 첫 안내) → Gemini 실패로 로컬 Qwen 지침 → 카메라 오프라인 → 정상 복귀.

### 테스트

```powershell
python -m unittest discover -s gui/tests -t .
```

## 화면

- **구역 목록**: 연결된 Pi마다 카드를 하나씩 보여 줍니다. 온라인 여부, 위험도, 원시 센서값, 화재·조기 감지·카메라 오프라인·DEMO 배지를 표시하고, 카드를 누르면 상세 화면으로 갑니다.
- **상세**
  - 좌측: Pi 카메라 영상(감지 박스 포함), 비전 상태 배지, 관제사 질의 입력
  - 우측: 센서(ADC 원시값/1023, 임계값), 위험도 게이지(LV 0~5), 로그, 현장 AI 지침(생성 출처·전환 이유)과 관제사 질의 답변
- **상단**: 경보 중인 구역이 있으면 빨간 배너와 이동 버튼이 나타납니다. 상태 칩은 MQTT 연결, Pi 온라인, 카메라, 센서 모드(DEMO/실센서), 관제 AI를 표시합니다.
- 보고 있는 구역은 브라우저 탭마다 따로 저장됩니다.

## 표시 규칙

| 항목 | 규칙 |
|---|---|
| 센서 | 가스·연기는 ADC 원시값(0~1023)입니다. ppm·%로 표시하지 않습니다. 테두리 색은 `config.SENSOR_THRESHOLDS`를 넘으면 빨강, 80% 이상이면 주황입니다 |
| 위험도 | 0~5 (0 정상 · 1 주의 · 2 경고 · 3 위험 · 4 긴급 · 5 재난). 경보 중에는 Pi와 같이 시작 단계를 유지하고, 이번 주기 계산값이 다르면 함께 표시합니다 |
| DEMO | Pi의 `SENSOR_MODE=demo`일 때 표시합니다 (가상 센서값) |
| 사진 오탐 차단 | 비전 상태가 `STATIC_PHOTO_BLOCKED` 또는 `HANDHELD_PHOTO_BLOCKED`일 때만 표시합니다 |
| 카메라 오프라인 | Pi가 `CAMERA_OFFLINE`을 보낼 때. 영상이 3초 이상 끊기면 "영상 수신 없음"으로 따로 표시합니다 |
| 신호 없음 | 마지막 status가 5초 이상 지났거나 Pi가 offline(Last Will)일 때. 이때 위험도는 0으로 취급하고 옛 값을 보여 주지 않습니다 |
