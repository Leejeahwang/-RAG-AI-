# Vision 후속 수정 검증 — 2026-10-18 (KST)

브랜치: codex/vision-rag-voice · 작업 시작 커밋: 6f24c5b

## 같은 날 추가: NCNN 기본 경로 전환

아래 ONNX 검사 결과는 전환 전 기록입니다. 현재 기본값은
`vision/models/fire_smoke_ncnn_model/`의 NCNN 모델이며 입력은 640×640입니다.
로컬 `fire_smoke.pt`를 FP32, batch 1, CPU로 변환했습니다. fire/smoke 클래스와
모션 검증·경보 정책은 유지합니다. 상세 변경은 [DEV_LOG.md](DEV_LOG.md)에 기록했습니다.

| NCNN 전환 후 검사 | 결과 |
|---|---|
| 실제 변환·NCNN 실행 | 성공, `[1,3,640,640]` 입력, 2클래스 |
| 기존 전체 회귀 | 117개 통과, 7.274초 |
| 기존 알고리즘 검사 | Optical Flow·퓨전·실제 NCNN 검정 이미지·VLM 모의 결과 통과 |
| 실제 NCNN 검정 프레임 12개 | 12/12 SAFE; 평균 30.76ms, p50 30.93ms, p95 32.47ms |
| NCNN 첫 워밍업 | 76.15ms |
| Pi 5·실제 화재 정확도 | 미측정 |

실행 호스트는 동일한 Windows AMD64 / Python 3.12.4이며 NCNN 1.0.20260526,
PNNX 20260526, Ultralytics 8.4.22를 사용했습니다. 현재 PC의 검정 프레임 처리 시간이며
Pi 성능, 앱 전체 FPS 또는 실제 화재 정확도 비교 결과가 아닙니다.
원시 기록은 `scratch/vision_ncnn_runtime.json`, `scratch/vision_ncnn_regression.log`,
`scratch/vision_ncnn_algorithm.log`, `scratch/vision_ncnn_export.log`에 있습니다.
변환물의 원본·출력 해시와 버전은 모델 폴더의 `export_manifest.json`에 있습니다.

## 수정 내용

- 감지 계약 v1: 검증된 불꽃과 상승 연기를 분리. 워밍업·검증 중·차단·오류는 미확정.
- 불꽃과 연기의 최고 점수 후보를 개별 추적하고, 선택한 좌표와 점수 일치.
- 3회 연속 모션 검증을 실제 확정 조건으로 사용. 정지·후보 소멸·후보 교체·영상 크기 변경·카메라 중단 후 새로 검증.
- Level 2 고정 한국어 경고 및 콘솔 알림. 중복 억제, 정상 확인 후 재허용,
  이전 일반 답변 폐기, 비상 대피 안내 우선순위 유지.
- 카메라 수집 완료 시각·순번 전달, 중단·시간 초과 프레임 미사용.
- main_test.py에서도 전체 결과를 퓨전에 전달하고 연기를 SAFE로 표시하지 않도록 수정.
  평시 Q&A 모드의 비상 음성 비활성화 정책은 유지.
- Pi에서도 실행 가능한 실제 모델·웹캠 점검 도구와 최신 실행 문서 추가.

## 실행 결과

| 검사 | 결과 | 범위 |
|---|---|---|
| unittest discover -s tests -v | **117개 통과**, 6.794초 | 감지 계약, 제어된 후보·모션의 메인 연결, L2→L4, 불꽃 demo 격상, 음성 우선순위, 카메라 중단, 기존 RAG·음성·구역 HTTP 회귀 |
| vision/test_unit_verification.py | **전체 통과**, 종료 코드 0 | 실제 Optical Flow 합성 입력 5종, 센서 퓨전 5종, 실제 ONNX 검정 이미지, VLM 모의 결과 |
| 실제 ONNX 검정 프레임 | **12/12 SAFE** | 워밍업 후 평균 29.60ms, p50 29.13ms, p95 32.67ms. 첫 워밍업 243.86ms |
| 실제 카메라 | **미완료: 0프레임** | 샌드박스 밖에서도 현재 연결된 Camera/Image 장치 없음. OpenCV 장치 열기 실패 |
| 라즈베리파이 실장치 | **미실행** | 현재 실행 호스트는 Windows AMD64. 접속할 Pi 장치가 제공되지 않음 |
| 소스 구문·변경 공백 검사 | 통과 | 변경된 Python 소스 compileall, git diff --check |

회귀는 일반 생성 결과가 늦게 도착하는 상황, 경고 중 새 질문, 진행 중인 비상 안내,
같은 프레임 중복, 불꽃 검증 중 가상 센서 격상 방지 등을 포함합니다.
회귀의 YOLO 후보와 모션 벡터는 제어된 입력이며 실제 화재 영상 정확도 검사는 아닙니다.
VLM은 시뮬레이션 검사만 수행했습니다. 외부 클라우드 요청·실제 발화·마이크는 사용하지
않았고 구역 경보 통신은 로컬 HTTP 송수신 테스트로 확인했습니다.

## 실제 모델 검사 환경

- Windows / AMD64 / Python 3.12.4. 프로젝트 권장 Python 3.11 및 Pi 결과가 아님.
- NumPy 1.26.4, OpenCV 4.10.0.84, Ultralytics 8.4.22,
  ONNX Runtime 1.26.0 CPUExecutionProvider, PyTorch 2.10.0.
- 모델: vision/models/fire_smoke.onnx.
- SHA-256: d533342c2749a075e50e8797370379c49154274b9559209d6091c2f96c6a23ce.
- BYPASS_MOTION_FILTER=false. 검정 프레임 12개, 소수 표본.
- 의존성은 프로젝트의 무시된 .venv에 준비했으며 전역 패키지를 교체하지 않음.

이 수치는 현재 PC의 검정 프레임 추론 지연입니다. 실제 화재 탐지 시간·음성 시작 지연,
연기 센서보다 빠른 시간, 실환경 오탐률·미탐률 또는 Pi 성능으로 해석하지 않습니다.

## 재현 자료

작업 환경의 scratch는 Git에서 제외됩니다. 원시 기록은 다음 파일에 있습니다.

- scratch/vision_regression.log: 최종 117개 테스트 출력.
- scratch/vision_algorithm.log: Optical Flow·퓨전·ONNX·VLM 모의 검사 출력.
- scratch/vision_runtime_host.json: 실제 호스트의 모델·카메라 검사 JSON.
- scratch/vision_runtime.json: 샌드박스 안에서 먼저 수행한 모델·카메라 검사 JSON.

```text
python -m unittest discover -s tests -v
python vision/test_unit_verification.py
python tools/check_vision_runtime.py --camera --seconds 30 --frames 30 --output scratch/vision_camera.json
```

전체 테스트에는 localhost 연결과 임시 파일 쓰기가 필요합니다. 이번 Windows 환경에서는
TEMP/TMP를 프로젝트 scratch/test_temp로 지정하고 샌드박스 밖에서 전체 회귀를 실행했습니다.
카메라 검사는 영상 저장·전송 없이 상태·시간만 기록합니다.

다음 실장비 작업은 [README.md](README.md)의 검증 표에 따라 웹캠을 연결해
정상 배경·사진·화면·연무·불꽃 조건을 기록하고, Pi에서 같은 자동 검사와 실제 센서·스피커의
Level 2 → 4/5 전환을 확인하는 것입니다. 실제 장비 검증은 아직 완료되지 않았습니다.
