# 실제 Pi ↔ 노트북 관제 연동 테스트 가이드

라즈베리파이를 가진 사람이 **혼자서** 아래 순서대로 진행하고, 마지막 결과표를 채워 공유하면 됩니다.
소요 시간은 설치 포함 약 1시간입니다.

## 무엇을 확인하나

```
라즈베리파이 main.py ──MQTT(Pi의 mosquitto, 1883)──▶ 노트북 대시보드 (streamlit)
```

| 테스트 | 확인할 것 |
|---|---|
| A. 연결·화면 | 노트북 대시보드에 Pi의 센서·카메라·위험도·경보가 뜨는가 |
| B. 지연 측정 | Pi → 노트북 전달 지연, 영상 장수 |
| C. 재연결 | 노트북 Wi-Fi·브로커·main.py를 껐다 켜도 자동으로 다시 붙는가 |
| D. 랜선 제거 | 네트워크가 끊겨도 Pi 혼자 사이렌·대피 방송을 계속하는가 |
| E. CPU 부하 | 발행 기능을 켰을 때 Pi CPU가 얼마나 더 쓰이는가 |

## 준비물

- 라즈베리파이 5 (기존 설치 완료: `rpi5_setup_guide.md`), 카메라, 스피커
- 노트북 1대 (Windows 기준. 대시보드 실행용)
- 두 기기가 **같은 네트워크**에 연결 (같은 공유기, 또는 휴대폰 핫스팟)
- 테스트 D용: Pi 랜선(유선) 또는 Pi Wi-Fi를 끌 수 있는 환경

> **중요**: 테스트 D는 Pi의 네트워크를 끊습니다. SSH로 접속해 있으면 SSH도 끊기므로, **Pi에 모니터·키보드를 직접 연결**하거나 `tmux` 안에서 `main.py`를 실행하세요.

---

## 1. Pi 준비 (약 15분)

### 1-1. 코드 받기

```bash
cd ~/-RAG-AI-          # rpi5_setup_guide.md 로 clone 한 폴더
git fetch origin
git checkout feature/gui-remote-dashboard
git pull
```

`main.py` 32번째 줄 근처에 `from gui import edge_publisher as edge`가 있으면 발행 코드가 들어간 버전입니다.

### 1-2. mosquitto 설치·설정

```bash
sudo apt install -y mosquitto mosquitto-clients
sudo tee /etc/mosquitto/conf.d/edge-saver.conf <<'EOF'
listener 1883 0.0.0.0
allow_anonymous true
EOF
sudo systemctl enable --now mosquitto
sudo systemctl restart mosquitto
```

확인:

```bash
sudo ss -ltnp | grep 1883        # 0.0.0.0:1883 이 보이면 정상 (127.0.0.1:1883 만 보이면 설정 파일 확인)
hostname -I                      # Pi IP 확인. 예: 192.168.0.50 → 아래에서 계속 사용
sudo ufw status                  # "active"면: sudo ufw allow 1883/tcp
```

### 1-3. main.py 실행

```bash
source .venv-py311/bin/activate      # rpi5_setup_guide.md 기준 가상환경 이름
python main.py
```

다른 터미널에서 발행 확인:

```bash
mosquitto_sub -h 127.0.0.1 -t 'edge/#' -v | grep -v /frame
```

1초마다 `edge/A/status {...}`가 나오면 Pi 쪽은 준비 완료입니다. (`A`는 `.env`의 `ZONE_ID`)

---

## 2. 노트북 준비 (약 10분)

### 2-1. 코드와 패키지

같은 브랜치(`feature/gui-remote-dashboard`)를 받습니다. GitHub에서 **Code → Download ZIP**으로 받아도 됩니다.

```powershell
cd <프로젝트 폴더>
pip install -r gui/requirements_dashboard.txt
```

### 2-2. Pi 연결 확인

```powershell
ping 192.168.0.50
Test-NetConnection 192.168.0.50 -Port 1883      # TcpTestSucceeded : True 가 나와야 함
```

`False`면 아래 [문제 해결](#문제-해결)을 먼저 보세요.

### 2-3. 대시보드 실행

```powershell
$env:MQTT_BROKER_HOST = "192.168.0.50"
$env:STT_ENABLED = "false"
streamlit run gui/dashboard.py
```

브라우저가 열리면 됩니다. RAG 패키지를 설치하지 않았다면 "관제 AI 꺼짐"이 표시되는데, **수신·표시 테스트에는 문제없습니다.**

---

## 3. 테스트 A — 연결·화면 확인 (5분)

1. 대시보드 상단에 `MQTT 192.168.0.50:1883` 칩이 초록색인지 확인합니다.
2. 구역 목록에 **A구역 카드**가 보이면 클릭합니다.
3. 다음이 보이는지 체크합니다.
   - [ ] `PI ONLINE`, `CAM LIVE` 칩 초록색
   - [ ] 왼쪽에 Pi 카메라 영상 (초당 2~3장 갱신, 감지 시 박스 표시)
   - [ ] 센서값이 `/1023`(가스·연기), `°C`(온도)로 표시, `DEMO · 가상 센서` 배지 (`SENSOR_MODE=demo`일 때)
   - [ ] 위험도 게이지 `LV 0 / 5`
4. Pi 터미널에서 `test fire` 입력:
   - [ ] 대시보드 상단에 **빨간 위급상황 배너**
   - [ ] 위험도 `LV 4 / 5` 이상, `Pi 경보·대피 방송 중` 배지
   - [ ] 현장 AI 지침에 첫 고정 안내 → 몇 초 뒤 `생성: Gemini` 또는 `로컬 Qwen`으로 바뀜
   - [ ] 15초 뒤 정상 복귀 시 배너가 사라지고 로그에 `정상 복귀, 경보 종료`
5. 카메라 앞에 휴대폰 화재 사진을 들어 보면 `🛡️ 사진 오탐 차단` 배지가 뜨는지 확인합니다 (비전 판정에 따라 다를 수 있음).

화면 캡처를 2장(정상, 경보 중) 남겨 두세요.

---

## 4. 테스트 B — 지연 측정 (3분)

대시보드는 켜 둔 채로, 노트북에 PowerShell 창을 하나 더 열어 실행합니다.

```powershell
python -m gui.measure_link --host 192.168.0.50 --seconds 60 --csv link_normal.csv
```

60초 뒤 결과가 출력됩니다. 결과표에 옮길 값은 다음과 같습니다.

- **왕복 지연 RTT 중앙값/p95**: 노트북 → Pi 브로커 → 노트북. 시계 동기화와 무관하게 정확합니다.
- **Pi→노트북 단방향 추정(RTT/2)**: Pi 안의 `main.py → 브로커` 구간은 같은 기기라 1ms 미만이므로, 이 값이 사실상 전달 지연입니다.
- **frame 장/초, 평균 KB**: 기본 설정이면 약 3장/초입니다.

> **화면 반영 지연** = 전달 지연 + 대시보드 화면 갱신 주기(카메라 0.5초, 나머지 1초)입니다. 보고서에는 "전달 지연 ○ms + 화면 갱신 최대 1초"로 적습니다.
> `status 지연(시계 기준)` 값은 두 기기 시계 차이가 그대로 더해지므로 참고만 하세요. 음수가 나오면 시계가 맞지 않는 것입니다.

가능하면 **경보 중**에도 한 번 측정합니다 (`test fire` 입력 직후 실행, `--seconds 30`).

---

## 5. 테스트 C — 재연결 (10분)

측정 도구를 계속 켜 둔 채로 진행하면, 끊김·재연결 시각이 자동으로 기록됩니다.

```powershell
python -m gui.measure_link --host 192.168.0.50 --csv link_reconnect.csv     # Ctrl+C 로 종료
```

| 순서 | 할 일 | 기대 결과 |
|---|---|---|
| C-1 | 노트북 Wi-Fi 끄기 → 20초 → 켜기 | 대시보드: 5초 안에 `신호 없음`, Wi-Fi 복구 후 약 10초 안에 자동 재연결. 측정 도구에 `🔴 끊김` → `🟢 연결됨` 기록 |
| C-2 | Pi에서 `sudo systemctl restart mosquitto` | Pi `main.py`는 멈추지 않고 계속 동작. 대시보드·측정 도구 모두 자동 재연결 |
| C-3 | Pi `main.py` 종료(`q`) → 다시 실행 | 종료 즉시 대시보드 `Pi 신호 없음`(online=false 수신), 재실행 후 다시 표시 |
| C-4 | Pi `main.py`를 `Ctrl+C` 대신 강제 종료(`kill -9 <PID>`) | 최대 15초 안에 `Pi 신호 없음` (브로커의 Last Will) |

각 항목마다 "끊김 → 다시 연결"까지 걸린 시간을 측정 도구의 사건 기록에서 읽어 결과표에 적습니다.

---

## 6. 테스트 D — 랜선 제거 시 Pi 단독 방송 (10분)

`test fire`의 경보 유지 시간(15초)이 짧아서, 이 테스트 동안만 늘립니다.

```bash
# Pi: config.py 맨 아래쪽
DEMO_ALARM_HOLD_SECONDS = 120.0      # 테스트 후 반드시 15.0 으로 되돌리기
```

`main.py`를 다시 실행하고 진행합니다.

1. 노트북에서 측정 도구를 실행합니다: `python -m gui.measure_link --host 192.168.0.50 --csv link_unplug.csv`
2. Pi에서 `test fire`를 입력합니다. 사이렌과 첫 안내 방송이 나오고, 대시보드에 경보가 뜨는지 확인합니다.
3. **Pi 랜선을 뽑습니다.** Pi가 Wi-Fi라면 Pi 터미널에서 `sudo ip link set wlan0 down`을 실행합니다.
4. 60초 동안 관찰합니다.
   - [ ] **Pi**: 사이렌·대피 방송이 끊기지 않고 **약 25초마다 대피 방송 반복**
   - [ ] **Pi** 터미널에 오류가 계속 쏟아지거나 멈추지 않음
   - [ ] **대시보드**: 5초 안에 `Pi 신호 없음`, 15초 안에 상단 `MQTT 끊김` 칩 (옛 위험도를 계속 보여 주지 않음)
5. **랜선을 다시 꽂습니다** (`sudo ip link set wlan0 up`).
   - [ ] 대시보드가 자동으로 다시 연결되고, **현재 경보 상태(LV, 경보 중, AI 지침)**가 바로 다시 표시됨
   - [ ] 측정 도구에 끊김 구간 길이와 재연결 시각이 기록됨
6. 끝나면 `config.py`를 `DEMO_ALARM_HOLD_SECONDS = 15.0`으로 되돌립니다.

> 끊긴 동안 생긴 이벤트(경보 시작·AI 지침 등)는 재연결 순서에 따라 대시보드 이력에서 빠질 수 있습니다. 현재 상태 표시는 다시 맞춰지므로 정상입니다.

---

## 7. 테스트 E — Pi CPU 부하 (10분)

발행 기능을 끈 상태와 켠 상태를 각각 60초씩 비교합니다.

```bash
sudo apt install -y sysstat

# ① 발행 끔
EDGE_PUBLISH=false python main.py
#   다른 터미널:
pidstat -u -p $(pgrep -f "python main.py" | head -1) 5 12       # 60초, 마지막 Average 줄의 %CPU 기록

# ② 발행 켬 (기본값: status 1초 + 영상 3장/초)
python main.py
#   같은 pidstat 명령으로 측정

# ③ (선택) 영상만 끔
EDGE_FRAME_FPS=0 python main.py
```

세 경우 모두 카메라 앞 장면은 같게 둡니다 (평상시 화면, 경보 없음).

---

## 결과표 (채워서 공유)

| 항목 | 결과 | 비고 |
|---|---|---|
| 테스트 일시 / 네트워크 | | 예: 10/14, 연구실 공유기 / 핫스팟 |
| A. 대시보드 표시 | ✅ / ❌ | 안 된 항목 |
| B. RTT 중앙값 / p95 | ms / ms | |
| B. Pi→노트북 추정 지연 (RTT/2) | ms | |
| B. 영상 장/초, 평균 크기 | 장/초, KB | |
| C-1 노트북 Wi-Fi 재연결 | 초 | |
| C-2 브로커 재시작 후 재연결 | 초 | Pi main.py 멈춤 여부 |
| C-3 main.py 재시작 표시 | ✅ / ❌ | |
| C-4 강제 종료 후 신호 없음 표시 | 초 | |
| D. 랜선 제거 중 Pi 방송 유지 | ✅ / ❌ | 반복 방송 간격 |
| D. 대시보드 신호 없음 표시 | 초 | |
| D. 재연결 후 상태 복구 | 초 | |
| E. CPU ① 발행 끔 | % | |
| E. CPU ② 발행 켬 | % | 증가량 = ② − ① |
| E. CPU ③ 영상 끔 | % | |

**함께 보낼 것**: 측정 도구 출력(터미널 텍스트 복사), `link_*.csv` 3개, 대시보드 캡처 2장(정상, 경보 중).

---

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `Test-NetConnection ... False` | Pi `ss -ltnp`에 `0.0.0.0:1883`이 있는지(설정 파일), 두 기기가 같은 네트워크인지, Pi `ufw` 방화벽 |
| ping은 되는데 1883만 안 됨 | 학교·회사 Wi-Fi는 기기 간 통신을 막는 경우가 많습니다(AP 격리). **휴대폰 핫스팟**에 둘 다 연결해 보세요 |
| 대시보드에 `MQTT 연결 중`만 뜸 | `$env:MQTT_BROKER_HOST`를 설정한 **같은 창**에서 `streamlit run`을 실행했는지 확인. 또는 `.env`에 `MQTT_BROKER_HOST=192.168.0.50` 추가 |
| 연결은 되는데 구역이 안 뜸 | Pi에서 `mosquitto_sub ... edge/#`에 메시지가 나오는지 확인. 안 나오면 `main.py`가 발행 코드 버전인지(1-1), `.env`에 `EDGE_PUBLISH=false`가 있는지 확인 |
| 상태는 뜨는데 영상만 없음 | Pi 카메라가 `CAM OFFLINE`인지(카메라 문제), `.env`에 `EDGE_FRAME_FPS=0`이 있는지 확인 |
| Pi에서 `ModuleNotFoundError: gui` | 프로젝트 **루트 폴더**에서 `python main.py`를 실행했는지 확인 |
| Pi에서 `No module named paho` | `pip install paho-mqtt` (가상환경 안에서) |
| 시간이 계속 틀어짐 / status 지연이 음수 | 정상입니다(시계 차이). RTT 값을 사용하세요. 맞추려면 Pi `timedatectl`로 NTP 동기화 확인 |

관련 문서: 메시지 형식 [PROTOCOL.md](PROTOCOL.md), `main.py` 연결 코드 [MAIN_INTEGRATION.md](MAIN_INTEGRATION.md), 대시보드 사용법 [README.md](README.md)
