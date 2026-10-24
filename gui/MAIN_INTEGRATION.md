# main.py 관제 발행 연결 방법

Pi의 `main.py`가 판단한 결과를 관제 대시보드로 보내려면 `main.py`에 아래 코드(import 1줄, 연결·종료 각 1곳, 발행 6곳)를 넣습니다.
발행 코드는 모두 `gui/edge_publisher.py`에 있고, `main.py`는 호출만 합니다.

> **기준 코드 (2026-10-24 갱신)**: `integration/vision-rag-voice`(10/18, Gemini 음성·비상 음성 캐시)와
> `codex/vision-rag-voice`(10/18, NCNN 비전·Level 2 경고)를 합친 `main.py`입니다. 두 브랜치는 충돌 없이 합쳐지며,
> `feature/gui-remote-dashboard`의 `main.py`에는 아래 코드가 이미 들어 있습니다.
> 화재 구역(`zone_id`)·안내 구역(`self.local_zone`)·감지 구역(`self.detection_zone`)이 나뉜 구조에 맞췄습니다.

## 원칙

- **main.py를 멈추지 않습니다.** 브로커가 없거나 끊겨도 모든 호출은 즉시(1ms 이하) 반환하고 예외를 밖으로 내보내지 않습니다. 재연결은 백그라운드에서 자동으로 합니다.
- **판단은 그대로 둡니다.** 위험도·경보·대피 방송 로직은 바꾸지 않고, 계산된 값을 옮기기만 합니다.
- **네트워크가 끊겨도 Pi는 혼자 방송을 계속합니다.** 발행 실패는 경보·TTS에 영향을 주지 않습니다.

## 넣을 코드 (diff)

`+` 줄만 추가하면 됩니다.

```diff
 from voice.tts import TTSHelper
+from gui import edge_publisher as edge
```

**① initialize()** — 첫 연결 준비(약 0.15초)를 감시 루프 밖에서 끝냅니다.

```diff
         fire_detector.warmup()
+        edge.start()
```

**② _trigger_rag_alert() — 경보 시작.** 새 경보일 때만(같은 구역 재감지 분기는 제외) 보냅니다.
첫 안내 문장(`first_guidance`, 예: "B구역에서 화재 위험이…")과 화재·안내 구역을 함께 보냅니다.

```diff
             send_alert(zone=zone_id, local_zone=self.local_zone, risk_level=level, sensor_details=sensor_info)
+            edge.publish_event("alarm_start", level=level, details=sensor_info, text=first_guidance,
+                               provider="fixed", fire_zone=zone_id, local_zone=self.local_zone)
             print(f"\n[첫 비상 안내] {first_guidance}")
```

**③ _trigger_rag_alert() — 구역 대피로.** 등록 구역 자료로 만든 대피로를 방송할 때 함께 보냅니다.

```diff
                 self._cached_evac_guidance += "\n" + zone_guidance
+                edge.publish_event("guidance", text=zone_guidance, provider="zone", emergency=True,
+                                   fire_zone=zone_id, local_zone=self.local_zone)
```

**④ _clear_alarm() — 정상 복귀.** 다른 구역 경보가 남아 있으면 이 줄까지 오지 않고 그 경보로 다시 시작합니다.

```diff
             stop_siren(force=True)
+            edge.publish_event("alarm_end")
             print("\n[시스템] 정상 복귀, 반복 비상 방송 종료")
```

**⑤ _guidance_worker() — AI 지침.** 실제로 방송한 문장 `text`(중복 안내를 걸러 낸 결과)를 넘깁니다.
비상 지침인데 `text`가 비었으면(AI 실패, 추가 수칙 없음) 발행 모듈이 보내지 않습니다.
`result`의 속성은 발행 모듈 안에서 읽습니다. main.py에서 꺼내다 예외가 나면 이후 음성 안내까지 막히기 때문입니다.

```diff
                     print(f"[시간] 검색 {searched-started:.2f}s / 답변 {time.perf_counter()-searched:.2f}s")
+                    edge.publish_guidance(result, emergency=job["emergency"], text=text,
+                                          fire_zone=job.get("fire_zone"), local_zone=job.get("local_zone"))
```

**⑥ _monitor_once() — 매 감시 주기 상태.** `with self._state_lock:` 블록 마지막, `current_risk_stats` 바로 아래에 둡니다.

```diff
             self.current_risk_stats = (f"[{config.SENSOR_MODE}] T:{temp['temperature']}C G:{gas} S:{smoke} "
                                        f"CAM:{analysis.get('status', 'UNKNOWN')} | {label}")
+            edge.publish_monitor(temp=temp, gas=gas, smoke=smoke, risk=risk, analysis=analysis,
+                                 level=self.current_level, alarm=self._alarm_active,
+                                 frame=frame if fresh else None, fire_zone=self._event_zone)
```

- 0.15초마다 호출되지만 실제 status 발행은 1초에 한 번입니다. 위험도·경보·조기 감지·AI 모드가 바뀌면 즉시 보냅니다.
- `fire_zone`은 경보 중일 때만 status에 실립니다.
- `frame`은 참조만 넘기고, JPEG 축소·인코딩은 발행 모듈의 별도 스레드가 초당 3장 이하로 합니다.

**⑦ _handle_vision_warning() — Level 2 비전 경고.** Pi가 고정 경고 음성을 1회 방송할 때 보냅니다.

```diff
             send_alert(zone=self.detection_zone, local_zone=self.local_zone,
                        risk_level=2, sensor_details=risk["details"], ai_guidance=message)
+            edge.publish_event("warning", level=2, details=risk["details"], text=message, provider="fixed",
+                               fire_zone=self.detection_zone, local_zone=self.local_zone)
```

**⑧ cleanup()** — 종료 시 대시보드에 오프라인을 알립니다.

```diff
         if self._tts:
             self._tts.close()
+        edge.close()
```

## Pi 설정

### 1. 패키지

`paho-mqtt`와 `opencv-python`은 이미 `requirements.txt`에 있습니다. 브로커만 설치합니다.

```bash
sudo apt install -y mosquitto
```

### 2. 브로커가 랜으로 연결을 받도록 설정

mosquitto 2.x는 기본값이 **로컬 접속만 허용**입니다. 관제 PC가 접속하려면 설정 파일이 필요합니다.

```bash
sudo tee /etc/mosquitto/conf.d/edge-saver.conf <<'EOF'
listener 1883 0.0.0.0
allow_anonymous true
EOF
sudo systemctl enable --now mosquitto
sudo systemctl restart mosquitto
```

> 시연용 사설망 기준 설정입니다. 공개망에 연결한다면 `allow_anonymous false`와 사용자 비밀번호를 설정하세요. 공개 브로커(`test.mosquitto.org`)는 쓰지 않습니다.

### 3. `.env` (선택)

Pi는 기본값 그대로 자기 자신(127.0.0.1)의 브로커로 보냅니다. 바꿀 때만 추가하세요.

| 설정 | 기본값 | 설명 |
|---|---|---|
| `EDGE_PUBLISH` | `true` | `false`면 발행 전체를 끕니다 |
| `MQTT_BROKER_HOST` | `127.0.0.1` | Pi에서는 그대로 둡니다 |
| `MQTT_BROKER_PORT` | `1883` | |
| `EDGE_STATUS_INTERVAL` | `1.0` | status 최소 발행 간격(초) |
| `EDGE_FRAME_FPS` | `3` | 카메라 영상 초당 장수. `0`이면 영상을 보내지 않습니다 |
| `EDGE_FRAME_WIDTH` | `320` | 전송 영상 가로 픽셀 |
| `EDGE_JPEG_QUALITY` | `60` | JPEG 품질 |

구역 이름은 기존 `ZONE_ID`(A/B/C), 센서 모드는 기존 `SENSOR_MODE`를 그대로 씁니다.

## 연결 확인

Pi에서 `main.py`를 실행한 뒤 다른 터미널에서 다음을 실행합니다.

```bash
mosquitto_sub -h 127.0.0.1 -t 'edge/#' -v | grep -v /frame
```

1초마다 `edge/A/status`가 보이고, 아래 명령을 입력했을 때 `edge/A/event`가 나오면 정상입니다 (`SENSOR_MODE=demo`).

| 입력 | 나와야 할 event |
|---|---|
| `test fire` | `alarm_start`(fire_zone=A) → `guidance`(provider=zone) → AI 수칙이 있으면 `guidance` |
| `test fire B` | 다른 구역(B) 경보 수신: `alarm_start`(fire_zone=B, local_zone=A) → `guidance`(zone) |
| `test clear B` | B구역 경보 해제 → `alarm_end` |
관제 PC에서는 `MQTT_BROKER_HOST=<Pi IP>`로 대시보드를 실행합니다 (`gui/README.md`).

## 검증 기록

### 2026-10-24 (통합 10/18 + codex 10/18 기준, Windows PC)

- 위 코드를 넣은 `main.py`로 프로젝트 테스트 140개(팀원 추가분 포함)를 실행했습니다. 브로커 없음, 발행 기록용 가짜 클라이언트 모두 140/140 통과했습니다.
- 같은 실행에서 `alarm_start`·`guidance`(zone·AI)·`alarm_end`·`warning` 이벤트가 모두 발행되고, 다른 구역 경보 수신(화재 B / 안내 A 등)의 구역 값이 맞게 실리는 것을 확인했습니다.
- 가짜 Pi와 로컬 브로커로 대시보드를 띄워 브라우저 점검 17/17 통과: Level 2 노란 배너·경고 이력, 화재 A구역 빨간 배너, "화재 B구역 → A구역 안내 중", 구역 대피로·AI 수칙 이력, 버튼·입력 조작.
- **실제 `main.py` 실행 점검**: 실제 NCNN 비전 모델(임시로 `ncnn` 설치)·RAG 인덱스·Ollama로 `main.py`를 띄우고(카메라는 검은 화면, 음성은 무음 대체) 로컬 화재 → 정상 복귀 → B구역 경보 수신 → 해제 → Level 2 경고를 차례로 실행했습니다. 브로커로 나간 event 9개가 순서·구역 값 모두 맞았고, 그 메시지를 대시보드 수신부에 그대로 넣어 처리 실패 0건을 확인했습니다.
- 실제 Pi·카메라·스피커·mosquitto 환경은 아직 측정하지 않았습니다.

### 2026-10-10 (통합 10/9 기준)

- 위 diff를 `main.py` 복사본에 적용한 뒤 기존 `tests/test_integration.py` 10개를 실행했습니다. 브로커 없음, 가짜 브로커 모두 10/10 통과했습니다. 원본 `main.py`는 수정하지 않았습니다.
- 같은 실행에서 `alarm_start`·`guidance`·`alarm_end` 이벤트와 status가 발행되는 것을 확인했습니다.
- 로컬 MQTT 브로커(amqtt)로 브로커를 강제로 종료했다가 다시 켰습니다. 발행 호출은 최대 3.7ms 안에 반환했고, Pi 쪽 발행기와 대시보드 모두 자동으로 재연결했습니다. 첫 호출만 연결 준비 때문에 약 0.15초가 걸리며, ①의 `edge.start()`로 감시 루프 밖으로 옮깁니다.
- 실제 Pi·mosquitto·랜 환경, Pi CPU 부하는 아직 측정하지 않았습니다.

## 알려진 한계

- 브로커가 재시작되는 동안 생긴 이벤트는, 대시보드가 다시 구독하기 전에 도착하면 **이력에서 빠질 수 있습니다**. 다만 현재 상태(경보 여부, 위험도, AI 지침)는 retained status로 복구되므로 화면 표시는 맞습니다.
- 위험도는 Pi가 보낸 값을 그대로 씁니다. 경보 중에는 `main.py`처럼 경보 시작 단계 이상이 유지되고, 이번 주기 계산값은 `fused_level`로 따로 보냅니다.
