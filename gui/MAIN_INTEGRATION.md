# main.py 관제 발행 연결 방법

Pi의 `main.py`가 판단한 결과를 관제 대시보드로 보내려면 `main.py`에 아래 **7줄(호출 6곳 + import 1줄)**을 넣습니다.
발행 코드는 모두 `gui/edge_publisher.py`에 있고, `main.py`는 호출만 합니다.

## 원칙

- **main.py를 멈추지 않습니다.** 브로커가 없거나 끊겨도 모든 호출은 즉시(1ms 이하) 반환하고 예외를 밖으로 내보내지 않습니다. 재연결은 백그라운드에서 자동으로 합니다.
- **판단은 그대로 둡니다.** 위험도·경보·대피 방송 로직은 바꾸지 않고, 계산된 값을 옮기기만 합니다.
- **네트워크가 끊겨도 Pi는 혼자 방송을 계속합니다.** 발행 실패는 경보·TTS에 영향을 주지 않습니다.

## 넣을 코드 (diff)

통합 브랜치 `main.py` 기준입니다. `+` 줄만 추가하면 됩니다.

```diff
 from voice.tts import TTSHelper
+from gui import edge_publisher as edge
```

**① initialize()** — 첫 연결 준비(약 0.15초)를 감시 루프 밖에서 끝냅니다.

```diff
         _ = self.tts
         fire_detector.warmup()
+        edge.start()
```

**② _trigger_rag_alert()** — 경보 시작. 첫 고정 안내도 함께 보냅니다.

```diff
             trigger_alarm(level, sensor_info)
             send_alert(zone=zone_id, risk_level=level, sensor_details=sensor_info)
+            edge.publish_event("alarm_start", level=level, details=sensor_info,
+                               text=EMERGENCY_GUIDANCE, provider="fixed")
```

**③ _clear_alarm()** — 정상 복귀.

```diff
             self.tts.stop()
             stop_siren(force=True)
+            edge.publish_event("alarm_end")
             print("\n[시스템] 정상 복귀, 비상 방송 종료")
```

**④ _guidance_worker()** — AI 지침 생성 결과. `result`를 그대로 넘깁니다.
(속성을 main.py에서 꺼내면, 예외가 났을 때 바로 아래 음성 안내까지 막힙니다.)

```diff
                     print(f"\n[AI: {result.provider}] {result.text}")
+                    edge.publish_guidance(result, emergency=job["emergency"])
                     print(f"[시간] 검색 {searched-started:.2f}s / 답변 {time.perf_counter()-searched:.2f}s")
```

**⑤ _monitor_once()** — 매 감시 주기의 상태. `with self._state_lock:` 블록 마지막, `current_risk_stats` 바로 아래에 둡니다.
경보가 같은 주기에 시작되면 `alarm=True`가 같은 메시지에 실립니다.

```diff
             self.current_risk_stats = (f"[{config.SENSOR_MODE}] T:{temp['temperature']}C G:{gas} S:{smoke} "
                                        f"CAM:{analysis.get('status', 'UNKNOWN')} | {label}")
+            edge.publish_monitor(temp=temp, gas=gas, smoke=smoke, risk=risk, analysis=analysis,
+                                 level=self.current_level, alarm=self._alarm_active,
+                                 frame=frame if fresh else None)
```

- 0.15초마다 호출되지만 실제 status 발행은 1초에 한 번입니다. 위험도·경보·조기 감지 상태가 바뀌면 즉시 보냅니다.
- `frame`은 참조만 넘기고, JPEG 축소·인코딩은 발행 모듈의 별도 스레드가 초당 3장 이하로 합니다.

**⑥ cleanup()** — 종료 시 대시보드에 오프라인을 알립니다.

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

1초마다 `edge/A/status`가 보이고, `test fire`를 입력하면 `edge/A/event`에 `alarm_start`가 보이면 정상입니다.
관제 PC에서는 `MQTT_BROKER_HOST=<Pi IP>`로 대시보드를 실행합니다 (`gui/README.md`).

## 검증 기록 (2026-10-10, Windows PC)

- 위 diff를 `main.py` 복사본에 적용한 뒤 기존 `tests/test_integration.py` 10개를 실행했습니다. 브로커 없음, 가짜 브로커 모두 10/10 통과했습니다. 원본 `main.py`는 수정하지 않았습니다.
- 같은 실행에서 `alarm_start`·`guidance`·`alarm_end` 이벤트와 status가 발행되는 것을 확인했습니다.
- 로컬 MQTT 브로커(amqtt)로 브로커를 강제로 종료했다가 다시 켰습니다. 발행 호출은 최대 3.7ms 안에 반환했고, Pi 쪽 발행기와 대시보드 모두 자동으로 재연결했습니다. 첫 호출만 연결 준비 때문에 약 0.15초가 걸리며, ①의 `edge.start()`로 감시 루프 밖으로 옮깁니다.
- 실제 Pi·mosquitto·랜 환경, Pi CPU 부하는 아직 측정하지 않았습니다.

## 알려진 한계

- 브로커가 재시작되는 동안 생긴 이벤트는, 대시보드가 다시 구독하기 전에 도착하면 **이력에서 빠질 수 있습니다**. 다만 현재 상태(경보 여부, 위험도, AI 지침)는 retained status로 복구되므로 화면 표시는 맞습니다.
- 위험도는 Pi가 보낸 값을 그대로 씁니다. 경보 중에는 `main.py`처럼 경보 시작 단계 이상이 유지되고, 이번 주기 계산값은 `fused_level`로 따로 보냅니다.
