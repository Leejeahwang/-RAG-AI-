# Vision 실행 계약과 검증

담당: 박규태 · 갱신: 2026-10-18 · 기준: codex/vision-rag-voice

## 기본 모델: NCNN FP32, 640×640

`vision/models/fire_smoke.pt`의 같은 fire/smoke 가중치를 NCNN으로 변환해
`vision/models/fire_smoke_ncnn_model/`에서 읽습니다. `config.VISION_MODEL_PATH`로
모델 경로를 관리하며 추론은 CPU, `imgsz=640`, `rect=False`로 고정합니다.
카메라 영상 크기와 모델의 정사각형 입력 크기는 별도입니다. 종횡비를 유지해
리사이즈하고 패딩하며, 모션 검증에는 원래 카메라 프레임과 그 좌표를 사용합니다.
불꽃·연기 모션 검증과 Level 2/4/5 경보 계약은 유지합니다.

변환 도구 준비 및 실행:

```text
python -m pip install -r requirements_vision_export.txt
python tools/export_vision_ncnn.py
python tools/check_vision_runtime.py --frames 12 --output scratch/vision_ncnn_runtime.json
```

변환은 로컬 `.pt`만 사용하며 다른 가중치를 내려받지 않습니다. FP32, batch 1로
변환하고 실제 NCNN 검정 프레임 실행 후 배치합니다. 기존 출력 폴더는 덮어쓰지
않으므로 재변환 시 `--output vision/models/fire_smoke_reexport_ncnn_model`처럼
새 폴더를 지정하고 `VISION_MODEL_PATH`도 같은 경로로 설정합니다.
모델 폴더에는 `model.ncnn.param`, `model.ncnn.bin`, `metadata.yaml`,
`export_manifest.json`이 필요합니다. manifest는 원본·변환물 해시와 도구 버전을 기록합니다.
기본 NCNN 폴더의 위 4개 파일은 이 브랜치에 명시적으로 추적하므로 clone/pull에 포함됩니다.
일반 `models/` 무시 규칙은 유지합니다. 다른 이름으로 재변환한 모델은 별도 복사하거나
명시적으로 Git에 추가해야 합니다. 프로젝트 폴더를 수동 복사할 때는 모델 폴더도 포함하세요.
실행에는 `ncnn`이 필요하고 `pnnx`는 변환할 때만 필요합니다.

모델 누락·불완전·추론 오류는 감지 오류로 보고하며 다른 모델로 자동 전환하지 않습니다.
이전 ONNX와 명시적으로 비교할 때만 `VISION_MODEL_PATH=vision/models/fire_smoke.onnx`를
설정합니다. 환경변수 변경 후 앱을 재시작해야 합니다. ONNX는 음성 등 다른 기능에도
사용하므로 ONNX Runtime 의존성을 제거하지 않습니다.

현재 PC의 변환·검정 프레임 결과가 Pi 5 FPS 또는 실제 화재 정확도를 입증하지는
않습니다. Pi에서 같은 자료로 FPS·최초 감지 지연·미탐·오경보를 비교해야 합니다.

현재 실행 경로는 camera_worker_thread → vision_bridge.frame_snapshot →
fire_detector.detect_fire → sensors.fusion.calculate_risk_level →
main.EdgeSaver._monitor_once 입니다. cctv_service.py의 start_cctv_service는
독립 디스크 스캔용 과거 실행부이며 통합 음성·구역 경보를 실행하지 않습니다.
main_test.py도 전체 감지 결과와 수집 시각·번호를 사용하되, 평시 질의응답 전용이라
Level 2 경고와 Level 4·5 비상 음성은 실행하지 않습니다. gui/workers.py는 미통합
GUI 초안이며 현재 CLI 경보 정책이 적용된 실행부가 아닙니다.
수집 시각은 카메라 워커에서 읽기·디코딩을 마친 호스트 시각이며 센서 노출 시각은 아닙니다.

## 감지 결과 계약 v1

detect_fire는 성공·대기·차단·오류 모두 아래 공통 필드를 반환합니다.

| 필드 | 의미 |
|---|---|
| contract_version | 1 |
| fire_detected / is_real_fire | 모션으로 검증한 불꽃. 검증 중이면 둘 다 false |
| is_real_smoke | 상방 확산 모션으로 검증한 연기. 연기만 검증되면 fire_detected는 false |
| is_static_photo | 현재 선택한 두 클래스 후보가 모두 정지·강체 움직임으로 차단됨 |
| demo_bypass | demo 모드에서만 허용한 명시적 시연 우회. 실제 불꽃 검증을 뜻하지 않음 |
| status | SAFE, WARMING_UP, EVALUATING_*, REAL_*, *_BLOCKED 또는 오류 상태 |
| confidence / box | 최종 선택한 같은 후보의 YOLO 점수와 좌표. 실제 화재 확률을 뜻하지 않음 |
| observations | 불꽃·연기별 후보, 검증 상태, 연속 횟수·상방 비율·난류 점수 |

오류는 MODEL_NOT_INITIALIZED, ANALYSIS_ERROR, MOTION_ERROR, NO_RESULT,
INVALID_INPUT, FILE_NOT_FOUND로 구분하며 위험 확정 플래그는 모두 false입니다.
fusion은 과거 bool 및 dict 호출도 지원합니다. 과거의
fire_detected=true/is_real_smoke=true 조합은 연기 조기 감지로 해석합니다.

불꽃·연기는 각각 가장 신뢰도가 높은 후보 한 개를 별도의 분석기로 추적합니다.
첫 프레임은 워밍업이며 그 뒤 3개의 연속 유효 모션 쌍을 확인합니다.
즉 초기 상태에서는 최소 4개의 서로 다른 프레임이 필요합니다.
중간 실패, 후보 소멸, 겹침 비율 0.2 미만인 후보 교체, 해상도 변경,
카메라 중단·오래된 프레임은 해당 시간축 상태를 초기화합니다.
여러 객체를 각각 추적하는 기능은 아직 없습니다.

## 경보 정책

| 비전·센서 증거 | 결과 | 실제 동작 |
|---|---|---|
| 대기·사진 차단·오류, 센서 정상 | Level 0 | 상태 표시. 정상의 실환경 정확도를 입증하는 의미는 아님 |
| 검증된 연기 또는 불꽃, 센서 정상 | Level 2 | 발생 구역을 포함한 고정 한국어 경고 1회 + 콘솔 알림 |
| 검증된 연기·불꽃 + 센서 1개 반응 | Level 4 | 기존 긴급 안내, 구역 대피로, 추가 대응 수칙 |
| 검증된 연기·불꽃 + 센서 2개 이상 반응 | Level 5 | 기존 재난 경보·안내 |
| 비전 미확정 + 센서 1개 / 2개 이상 반응 | Level 1 / 3 | 기존 센서 단독 위험도 정책 |

Level 2는 LLM·네트워크를 기다리지 않으며 사이렌, 반복 대피 방송 또는 HTTP
화재 이벤트를 발행하지 않습니다. 상승 연기와 불꽃 경고를 각각 한 번 안내할 수
있고 불꽃 경고 후 연기 경고로 되돌아가 반복하지 않습니다. 일반 답변이 생성 중이면
이전 결과를 폐기하고 경고를 우선합니다. 경고 발화 중 새 질문은 대기 안내를 표시합니다.
진행 중인 Level 4·5 대피 안내는 Level 2가 끊지 않습니다.
건강한 SAFE 또는 사진 차단 관찰이 ALARM_RECOVERY_SECONDS 동안 유지되어야
새 경고를 허용합니다. 카메라 중단·오류·검증 중 상태는 해제 근거가 아닙니다.

demo의 DEMO_VISION_ESCALATION=true에서는 검증된 불꽃을 가상 센서로 Level 5까지
격상합니다. 검증 중 후보는 격상하지 않으며 hardware에서는 가상 센서를 쓰지 않습니다.
시연 우회는 SENSOR_MODE=demo와 BYPASS_MOTION_FILTER=true를 모두 만족할 때만
허용하고 결과를 DEMO_BYPASS로 표시합니다. 실환경 검증에서는 우회를 끄고,
센서 교차 검증을 점검할 때는 DEMO_VISION_ESCALATION도 false로 설정합니다.

## 자동 검증

프로젝트 의존성을 설치한 Python에서 저장소 루트를 기준으로 실행합니다.

```text
python -m unittest discover -s tests -v
python vision/test_unit_verification.py
python tools/check_vision_runtime.py --frames 12 --output scratch/vision_runtime.json
python tools/check_vision_runtime.py --camera --seconds 30 --frames 30 --output scratch/vision_camera.json
```

회귀 테스트는 제어된 YOLO 후보와 모션 벡터로 실제 감지기·모션 분석·퓨전·메인 연결을
검사합니다. 기존 비전 스크립트는 합성 영상의 실제 Optical Flow, 센서 퓨전, 실제
설정된 모델(기본 NCNN)의 검정 이미지 추론, VLM의 모의 응답을 검사합니다. 클라우드 VLM 실제 호출 검증은 아닙니다.
전체 테스트에는 로컬 HTTP 서버 및 임시 WAV 파일을 쓰는 테스트가 포함됩니다.
샌드박스에서 막히면 프로젝트 내 쓰기 가능한 TEMP/TMP와 localhost 접근이 필요합니다.

check_vision_runtime은 현재 OS·CPU 아키텍처·패키지 버전·모델 해시, 워밍업,
추론 평균·p50·p95, 카메라 프레임 나이를 JSON에 기록합니다.
카메라 영상은 저장·전송하지 않으며 음성·사이렌·클라우드를 호출하지 않습니다.
카메라가 없거나 모델·프레임 검사가 불완전하면 종료 코드 1을 반환합니다.
Windows 측정값을 Pi 측정값으로 표시하지 않습니다.

test_early_detection.py는 HSV·피부색 등 별도 후보 필터를 실험하는 HUD 도구입니다.
그 도구의 성공이 production detect_fire의 같은 동작을 보장하지 않습니다.
test_rpi_performance.py의 반응 시간 계산은 가정값 예시입니다.
실측 경보 시간 또는 19배 개선 증거로 사용하지 않습니다.

## 실제 웹캠·라즈베리파이에서 남은 검증

2026-10-18 현재 장치 결과는 VALIDATION_2026-10-18.md에 기록합니다.
아래 항목은 실장비·라벨 영상으로 수행하고 표본 수와 조건을 함께 기록해야 합니다.

| 항목 | 기록할 결과 |
|---|---|
| 정상 배경, 조명 변화, 사람 이동 | 시간당 오경보 수, 원시 후보·검증 상태 |
| 정지 사진, 손으로 흔든 사진, 위로 움직인 사진, 모니터 화재 영상 | 차단·검증 결과 및 미차단 사례 |
| 통제된 연무·불꽃 자료 | 시작 시각, 최초 후보, 모션 확정, Level 2 음성 시작 시각, 미탐 수 |
| 연기 + 실제 센서 반응 | Level 2 → 4/5 전환 시점, 중복 경보·음성 우선순위 |
| 카메라 분리·중단·복구 | 오래된 화면 미사용, 기존 경보 유지, 복구 후 새 모션 검증 |
| Pi 5 장시간 통합 동작 | 실제 보드·전원·냉각, CPU·메모리·온도, 지연 분포, 음성 동작 중 감시 |

Pi에 의존성·모델을 준비하고 같은 두 자동 테스트와 check_vision_runtime --camera를
실행합니다. 실제 센서·스피커를 연결한 main.py에서는 위 정책을 별도로 확인합니다.
이 도구의 모델 추론 시간은 전체 경보·음성 지연과 다릅니다.
위쪽으로 이동하는 화면·가습기·팬·조명 등의 움직임도 연기 조건에 맞을 수 있습니다.
현재 휴리스틱은 실연기·사진을 보편적으로 구분한다는 보장이 없으며,
3분 조기 감지·100% 오탐 제거 같은 수치는 실제 라벨 검증 없이 사용하지 않습니다.

VLMHazardAnalyzer는 현재 메인 감시에 연결되지 않은 별도 프로토타입입니다.
제공자·키 구분, 호출 주기, 결과 검증을 보완하기 전 완료 기능으로 발표하지 않습니다.
