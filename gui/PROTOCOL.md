# 관제 MQTT 메시지 형식 (v1)

Pi(`main.py` + `gui/edge_publisher.py`) → 브로커(Pi의 mosquitto) → 관제 대시보드(`gui/workers.py`).
코드상 정의는 `gui/protocol.py` 한 곳에 있고, 양쪽이 같은 함수로 만들고 읽습니다.

## 토픽

`{prefix}/{zone}/{kind}`. prefix 기본값은 `edge`, zone은 `config.ZONE_ID`(A/B/C)입니다.

| 토픽 | 언제 | QoS | retain | 내용 |
|---|---|---|---|---|
| `edge/{zone}/status` | 1초마다 + 위험도·경보·조기감지 변화 즉시 | 0 | ✅ | 현재 상태 전체 (JSON) |
| `edge/{zone}/event` | 경보 시작·종료, AI 지침 생성 시 | 1 | ❌ | 사건 1건 (JSON) |
| `edge/{zone}/frame` | 최대 `EDGE_FRAME_FPS`(기본 3) | 0 | ❌ | JPEG 바이트 (JSON 아님) |
| `edge/{zone}/online` | 연결 시 `true`, 정상 종료·연결 끊김(Last Will) 시 `false` | 1 | ✅ | `{"online": bool}` |

- status를 retain하므로 대시보드를 나중에 켜도 바로 마지막 상태를 받습니다.
- 대시보드는 `edge/+/+` 하나만 구독합니다.
- 마지막 status 수신 후 5초(`STATUS_INTERVAL × 5`)가 지나거나 online이 `false`면 그 구역을 **신호 없음**으로 표시하고, 위험도를 0으로 취급합니다.

## status

```json
{
  "v": 1,
  "zone": "A",
  "ts": 1791600000.12,
  "sensor_mode": "demo",
  "sensors": {"temperature": 75.0, "humidity": 41.2, "gas": 600, "smoke": 550},
  "risk": {
    "level": 5, "fused_level": 5, "label": "재난",
    "details": "🚨 대형 재난 화재 확정! (비전 감지 + 연기센서(천장), 가스센서, 고온감지)",
    "early": false
  },
  "vision": {
    "status": "REAL_FIRE_FLICKERING", "fire_detected": true,
    "real_smoke": false, "static_photo": false,
    "confidence": 0.86, "description": "🚨 [로컬 감지] 위험 요소: [FIRE] (AI 확신도: 86.0%)"
  },
  "alarm": true,
  "ai": {"text": "…대피하십시오.", "provider": "ollama", "fallback_reason": "ConnectTimeout", "ts": 1791600003.5}
}
```

| 필드 | 출처 (`main.py`) | 설명 |
|---|---|---|
| `ts` | Pi 시각 (epoch 초) | 표시용. 신호 지연 판정은 관제 PC의 수신 시각으로 합니다 |
| `sensor_mode` | `config.SENSOR_MODE` | `demo`면 대시보드에 **DEMO · 가상 센서** 배지를 표시합니다 |
| `sensors.gas`, `sensors.smoke` | `read_gas_level`, `read_smoke_level` | **ADC 원시값 0~1023**. ppm·%가 아닙니다. 임계값은 `config.SENSOR_THRESHOLDS` |
| `sensors.temperature`, `humidity` | `read_temperature` | °C, % |
| `risk.level` | `self.current_level` | 화면에 쓰는 위험도 **0~5**. 경보 중에는 경보 시작 단계 이상을 유지합니다 |
| `risk.fused_level` | `risk["level"]` | 이번 주기 `fusion.calculate_risk_level` 결과 |
| `risk.label` | `level` 기준 | 0 정상 · 1 주의 · 2 경고 · 3 위험 · 4 긴급 · 5 재난 |
| `risk.early` | `risk["is_early_detection"]` | 비전 조기 감지(연기 상승 등) |
| `vision.status` | `analysis["status"]` | 아래 표 참고 |
| `vision.*` | `analysis[...]` | `fire_detector.detect_fire` 결과를 그대로 옮깁니다 |
| `alarm` | `self._alarm_active` | Pi가 경보·대피 방송 중인지 |
| `ai` | 마지막 비상 지침 | `alarm_start`/비상 `guidance` 이벤트로 바뀌고 `alarm_end`에서 비워집니다. 현장 일반 질문 답변은 여기 들어가지 않습니다 |

### vision.status 값

| 값 | 의미 | 대시보드 표시 |
|---|---|---|
| `SAFE` | 감지 객체 없음 | 정상 |
| `WARMING_UP`, `INITIALIZING`, `BOX_TOO_SMALL` | 움직임 분석 준비 | 문구만 |
| `EVALUATING_FIRE_MOTION`, `EVALUATING_SMOKE_MOTION` | 움직임 분석 중 | 문구만 |
| `REAL_FIRE_FLICKERING` | 실제 불꽃 흔들림 확인 | 빨간 배지 |
| `REAL_SMOKE_RISING` | 연기 상승 확인 (조기 감지) | 조기 감지 배지 |
| `STATIC_PHOTO_BLOCKED`, `HANDHELD_PHOTO_BLOCKED` | 정지 사진·손에 든 사진 판정 | **사진 오탐 차단 배지 (이 두 값일 때만)** |
| `CAMERA_OFFLINE` | `main.py`가 프레임을 못 받음 | 카메라 오프라인 화면 |
| `MODEL_NOT_INITIALIZED`, `ANALYSIS_ERROR`, `MOTION_ERROR`, `INVALID_INPUT`, `NO_RESULT` | 비전 오류 | 문구만 |

## event

```json
{"v": 1, "zone": "A", "ts": 1791600000.2, "seq": 7, "type": "guidance",
 "text": "…", "provider": "ollama", "fallback_reason": "ConnectTimeout", "emergency": true}
```

| type | 호출 위치 | 필드 |
|---|---|---|
| `alarm_start` | `_trigger_rag_alert` | `level`, `details`, `text`(첫 고정 안내), `provider`=`fixed` |
| `guidance` | `_guidance_worker` | `text`, `provider`(`gemini`/`ollama`/`fixed`), `fallback_reason`, `emergency` |
| `alarm_end` | `_clear_alarm` | 없음 |

- `seq`는 Pi 프로세스마다 1부터 증가합니다. 대시보드는 `(seq, ts)`가 같은 메시지(QoS1 재전송)를 무시합니다.
- `provider` 표시 이름은 `gemini` → Gemini, `ollama` → 로컬 Qwen, `fixed` → 고정 안내입니다.
- `fallback_reason`은 `rag/provider.py`가 Gemini를 쓰지 못한 이유입니다(예: `Gemini API 키 없음`, `Gemini 재시도 대기 중`, `ConnectTimeout`).

## frame

- JPEG 바이트를 그대로 보냅니다. 가로 `EDGE_FRAME_WIDTH`(기본 320)로 줄이고, 감지 박스(`analysis["box"]`)와 비전 상태를 그립니다.
  - 빨강: 화재·연기 판정, 노랑: 사진 오탐 차단, 회색: 약한 감지
- 카메라가 오프라인이거나 프레임이 오래되면(`FRAME_MAX_AGE`) 보내지 않습니다. 대시보드는 3초 동안 새 프레임이 없으면 영상 없음으로 표시합니다.
- 대시보드는 JPEG 시그니처(`FF D8`)가 아니거나 2MB를 넘는 메시지는 버립니다.

## 호환성 규칙

- 필드를 **추가**하는 것은 v1 안에서 허용합니다. 대시보드는 모르는 필드를 무시합니다.
- 필드가 빠지거나 타입이 틀리면 대시보드는 기본값(0, 빈 문자열, false)으로 채웁니다. `level`은 0~5로 자릅니다.
- 필드 의미를 바꾸거나 없앨 때는 `mqtt_settings.SCHEMA_VERSION`을 올립니다.
