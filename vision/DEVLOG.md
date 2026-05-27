# 📓 Vision AI 개발 일지 (박규태)

이 문서는 엣지 세이버의 **Vision AI 모듈(`vision/camera.py` 등)**을 개발하면서 발생한 진행 상황, 문제점, 그리고 해결 방법을 매일 기록하는 용도입니다. 
(이 내용들이 쌓이면 주간 보고서 작성 시 그대로 복사해서 붙여넣을 수 있습니다.)

---

## 📅 2026-05-27

### 🚀 진행 내용
- **YOLOv11n 비교군 추가 및 9-Way 테스트 확장**: 새로 확보한 YOLOv11n 모델 가중치(`best_nano_111.pt`)를 비교군에 추가하고 OpenVINO FP16/INT8 포맷 변환을 성공적으로 수행하여 벤치마크 대상을 총 9종으로 확대함.
- **발열 추적 벤치마크 고도화**: 라즈베리파이 5의 시스템 온도 파일(`thermal_zone0`)을 읽어와 추론 루프 중 CPU의 `시작 온도 ➔ 최대 온도`를 트래킹하는 기능을 [benchmark.py](file:///c:/Users/wldnr/Desktop/RAG_SW/-RAG-AI-/vision/benchmark.py)에 심어 실측 발열 벤치마크를 진행함.
- **최종 모델 공식 선정**: 
  - `YOLOv11n (FP16)` 모델이 **108.8 ms**로 가장 빠른 속도를 갱신했으나, 감지 정확도(97.4% vs 96.1%)와 신뢰도(60.1% vs 54.6%)가 더 우수하고, 발열 상승 폭(+3.8℃ vs +6.1℃)이 더 안정적인 **`YOLOv8 (INT8)`**을 최종 실장 모델로 선정함.
- **우선순위 설정 반영**: 실시간 감지 데몬인 [fire_detector.py](file:///c:/Users/wldnr/Desktop/RAG_SW/-RAG-AI-/vision/fire_detector.py)와 라이브 테스트인 [live_test.py](file:///c:/Users/wldnr/Desktop/RAG_SW/-RAG-AI-/vision/live_test.py)의 우선 로드 모델 순서를 `YOLOv8 (INT8)`이 최우선이 되도록 세팅함.

### 💥 발생한 문제 (Issue)
- **가상환경 의존성 누락 및 디스크 공간 에러**: 라즈베리파이에서 `onnx` 및 `onnxruntime` 설치 도중 디스크 공간 부족(`Errno 28`)으로 설치 실패가 뜸.
- **모델 중복 로드**: 파일 매핑 및 보정 과정으로 인해 YOLOv11n INT8 테스트 시 FP16 파일이 로드되는 현상 식별.
- **PC 통합 환경 구동 중 라이브러리 누락**: `main.py` E2E 테스트 과정에서 윈도우 환경에 `pygame`, `pyttsx3`, `faiss-cpu`, `sentence-transformers`, `prompt-toolkit` 등의 패키지가 설치되어 있지 않아 실행 불가 에러 다수 발생.
- **PyAudio 컴파일 및 빌드 실패**: 윈도우 가상환경에서 `pyaudio`를 pip로 설치하려 했으나 `portaudio.h`가 없어 빌드가 실패(C1083)해 STT 모듈 임포트 실패로 크래시 발생.

### 💡 해결 및 배운 점 (Solution/TIL)
- **pip 캐시 정리**: `rm -rf ~/.cache/pip`로 pip 다운로드 캐시를 말끔히 비워 SD카드 여유 공간을 확보하고 패키지를 정상 재설치함.
- **의존성 업데이트 및 우회 설치**: 
  - `requirements.txt`에 신규 의존성들을 갱신하여 일괄 설치하도록 구조화함.
  - Python 3.13+ 버전과의 호환성 해결을 위해 pygame 대신 pre-built wheel이 정상 제공되는 `pygame-ce`(Community Edition)를 우회 설치하여 컴파일 에러 해결.
- **STT/PyAudio 예외 방어 및 텍스트 폴백**: 마이크 환경이나 `pyaudio` 라이브러리가 없는 PC 또는 엣지 시스템에서도 오류로 뻗지 않도록, `main.py`와 `voice/stt.py`에서 `pyaudio` 및 STT 관련 임포트부를 `try-except` 예외 처리하여 감싸고 `STT_AVAILABLE` 플래그를 통해 텍스트 전용 모드로 안전하게 자동 폴백되도록 보강함.
- **시스템 마진의 중요성**: 1초에 1장씩 추론하는 상황에서 YOLOv10m은 CPU 점유율이 60% 이상에 육박해 화재 발생 시 RAG(Ollama) 및 TTS/STT가 동시 실행될 때 보드가 죽을 리스크가 큼. 전체 E2E 생존력을 위해 성능 마진이 넉넉한 YOLOv8 INT8(120ms, 발열 51.8℃)이 최선의 배포 모델임을 종합 판단을 통해 배움.

---

## 📅 2026-05-24

### 🚀 진행 내용
- **9-Way 모델 벤치마크 비교군 구성**: 깃허브 `imnuman/fire-detection-yolo`에서 제공하는 YOLOv8 Base 모델 가중치(`new_yolov8n_yolov8n.pt`)를 다운로드 및 자동 배치하는 [download_new_model.py](file:///c:/Users/wldnr/Desktop/RAG_SW/-RAG-AI-/vision/download_new_model.py) 스크립트를 작성하여 모델을 확보함.
- **일괄 변환 및 양자화 파이프라인 가동**: `YOLOv10m (FP16)`, `New YOLOv8n (FP16)`, `New YOLOv8n (INT8)` 모델들을 OpenVINO 포맷으로 성공적으로 일괄 변환 완료.
- **벤치마크 스크립트 대폭 고도화**: captures 폴더 내 임의 1장에 대해 측정하던 기존 [benchmark.py](file:///c:/Users/wldnr/Desktop/RAG_SW/-RAG-AI-/vision/benchmark.py)를 `dataset` 내의 모든 화재/연기 이미지(77장)를 순차적으로 전수 조사하여 **진짜 화재/연기 클래스만 선별하여 감지율(%)과 신뢰도(%)를 산정**하도록 개편함.
- **데이터셋 기반 벤치마크 수행**: 9가지 모델의 용량, 평균 레이턴시, 화재 감지율, 평균 신뢰도를 측정 완료하고, 비전 관련 문서([benchmark_results.md](file:///c:/Users/wldnr/Desktop/RAG_SW/-RAG-AI-/vision/benchmark_results.md))로 문서화함.

### 💥 발생한 문제 (Issue)
- **data.yaml 경로 불일치**: 캘리브레이션 셋 경로가 이전 개발자의 윈도우 환경 절대 경로(`C:\Users\admin\...`)로 지정되어 있어 OpenVINO INT8 변환 중 이미지 탐색 실패 에러가 발생함.

### 💡 해결 및 배운 점 (Solution/TIL)
- **yaml 파일 경로 보정**: `vision/dataset/data.yaml`의 `path` 항목을 현재 사용자의 프로젝트 경로인 `c:/Users/wldnr/Desktop/RAG_SW/-RAG-AI-/vision/dataset`으로 갱신하여 캘리브레이션을 성공적으로 완료함.
- **New YOLOv8n 감지율 0.0%의 이유**: 깃허브 모델의 가중치가 일반 COCO 사물 학습 모델이라 77장의 화재/연기 사진에서 화재/연기 클래스를 전혀 감지하지 못하는 것이 확인됨. (오경보 차단용 모델로 부적합 판정)
- **양자화 시 신뢰도/감지율 상승 원리**: 캘리브레이션 튜닝 작업이 런타임 최적화와 결합하여 가중치 영점 스케일링을 보정해 주면서, YOLOv8 INT8 모델의 경우 오히려 FP32 원본(94.8%)보다 높은 감지율(97.4%)을 보임을 실측 및 규명함.

---

## 📅 2026-05-17

### 🚀 진행 내용
- 최신 **YOLOv10-Medium** 모델 도입 및 12만 장 대규모 데이터셋 기반의 강력한 화재/연기 감지기 이식 완료.
- YOLOv10-M 모델의 OpenVINO INT8 양자화 파이프라인 적용 및 기존 모델(YOLOv8)과의 4-way 벤치마크 테스트 수행.
- PC 환경에서 노트북 웹캠을 이용해 즉각적인 화재 감지 테스트가 가능하도록 `live_test.py` 유틸리티 스크립트 신규 제작.
- 라즈베리파이 환경의 발열 제어 및 자원 한계를 시뮬레이션하기 위해, 2초 주기 스캔 방식 및 50% 신뢰도 임계값을 적용한 `live_test_eco.py` (최대 자원 절약 버전) 스크립트 개발. 화재 감지 시 터미널에 긴급 경보 Print 기능 구현 완료.
- **벤치마크 결과:** YOLOv8 원본 대비 YOLOv10m(INT8)의 감지 신뢰도(Confidence)가 **34.6% -> 47.8%** 로 대폭 상승함을 증명.
- (참고: PC CPU 상에서 INT8 양자화 추론 시 오버헤드로 인해 Latency가 다소 증가(506ms -> 998ms)하는 현상이 측정되었으나, 실제 타겟인 ARM 아키텍처 라즈베리파이 환경에서는 OpenVINO SIMD 최적화를 통해 2~3배의 속도 향상이 보장되므로 문제없음 판단.)

---

## 📅 2026-05-15

### 🚀 진행 내용
- 타겟 디바이스인 **라즈베리파이 5**에 `feature/vision-Quantization` 브랜치를 이식하여 실전 벤치마크 테스트 수행
- `Raspberry Pi Connect`를 이용해 원격 웹 브라우저 환경에서 SSH 터미널 조작 및 테스트 실행
- **벤치마크 결과:** 인텔 기반 PC 환경과 달리 ARM 아키텍처에서는 **INT8(OpenVINO) 포맷이 119ms를 기록하며 가장 압도적인 추론 속도(원본 대비 약 2.5배)**를 보임을 증명함
- 해당 라즈베리파이 전용 테스트 결과를 `raspberry_pi_benchmark_results.md` 파일로 정리 및 보관

### 💥 발생한 문제 (Issue)
- 라즈베리파이에서 가상환경 세팅 중 `pip install` 시 `[Errno 28] No space left on device` (SD카드 용량 부족) 에러 발생
- 원인 분석 결과, `ultralytics`가 설치될 때 파이토치가 라즈베리파이에 불필요한 기가바이트(GB) 단위의 대용량 GPU/CUDA 패키지(`nvidia-cudnn`, `nvidia-cublas` 등)를 한꺼번에 다운로드하여 캐시를 꽉 채워버림

### 💡 해결 및 배운 점 (Solution/TIL)
- `rm -rf ~/.cache/pip` 명령어로 차버린 캐시 공간을 다시 확보함
- 파이토치 설치 시 `--index-url https://download.pytorch.org/whl/cpu` 옵션을 붙여 **CPU 전용 버전으로 강제 설치**하도록 유도하여 대용량 CUDA 다운로드 문제를 깔끔하게 해결함
- 엣지 디바이스(라즈베리파이 등)에 무거운 AI 패키지를 이식할 때는 GPU 호환 버전이 아닌 CPU 전용 빌드 휠(whl)을 명시적으로 지정해야 낭비를 막을 수 있다는 것을 배움

---

## 📅 2026-05-02

### 🚀 진행 내용
- `main` 브랜치의 원본 모델(`fire_smoke.pt`)을 기반으로 FP16, INT8 양자화(Quantization) 모델 생성 및 테스트 파이프라인 구축
- `ultralytics` 기반의 INT8 Export 스크립트(`export_int8.py`) 작성 및 캘리브레이션용 데이터셋(77장) 연동
- 라즈베리파이 CPU 아키텍처에 최적화된 **OpenVINO INT8** 포맷 채택 (용량 6MB -> 3.4MB로 43% 압축 성공)
- Base, FP16, INT8 세 가지 포맷의 디스크 용량, 평균 추론 시간, 감지 신뢰도를 자동 측정하는 벤치마킹 툴(`benchmark.py`) 자체 개발

### 💥 발생한 문제 (Issue)
- `ultralytics`를 활용해 TFLite 포맷으로 INT8 변환 시도 중, 파이썬 최신 버전(3.14.3)과 `tensorflow` 패키지 버전 호환성 문제로 인해 설치(AutoUpdate) 실패 에러 발생
- NCNN 포맷의 경우 현재 `ultralytics` 버전에서 `int8=True` 인자를 공식 지원하지 않아 Export 에러 발생

### 💡 해결 및 배운 점 (Solution/TIL)
- 텐서플로우 의존성을 탈피하고 CPU 추론에 강점이 있는 **Intel OpenVINO** 포맷으로 우회하여 INT8 변환 성공 (`nncf` 및 `openvino` 패키지 활용)
- 캘리브레이션 시 100장 미만의 데이터라도 대표성을 띤 이미지를 주입하면, 양자화로 인한 정확도 손실 대신 오히려 가중치 영점 조절이 잘 되어 신뢰도(Confidence)가 대폭 상승(34% -> 58%)하는 유의미한 현상을 벤치마크 결과로 증명함

---

## 📅 2026-04-01

### 🚀 진행 내용
- `camera.py` 수동 테스트 스크립트 삭제 및 라즈베리파이 실전용 `vision/cctv_service.py` 데몬 스크립트로 완전 대체
- Roboflow 클라우드 API 의존성 제거, 로컬 환경에서 `ultralytics` 패키지를 통해 오프라인으로 엣지 추론하도록 `vision/fire_detector.py` 구조 전면 개편
- 5초 주기 타임랩스 방식의 상시 화재 감시 스케줄링 파이프라인 완성 (모드 A 적용)
- 카메라 I/O 병목 및 윈도우 프리징 방지를 위해 백그라운드 카메라 전용 수집 스레드 분리 도입
- SD카드 용량 관리를 위해 지난 3일 치의 스캔 이미지를 자동으로 지우는 가비지 컬렉터 로직 추가

### 💥 발생한 문제 (Issue)
- Ultralytics 구동 시 `.pt` 파일 오픈에 `dill` 모듈이 필요하여 AutoUpdate가 돌았으나, 프로젝트 가상환경(`.venv`) 밖의 글로벌 파이썬에 잘못 설치되어 모델 연산이 죽는 에러 발생
- 메인 루프의 `time.sleep(5)` 로 인해 `cv2.imshow()`가 UI 갱신 이벤트(`cv2.waitKey()`)를 받지 못해 디버깅 창 전체가 '응답 없음(프리징)' 상태에 빠지는 현상 발견

### 💡 해결 및 배운 점 (Solution/TIL)
- 가상환경의 터미널 파이썬(`pip.exe`)을 강제로 지정하여 `dill` 모듈을 격리된 공간 내부에 재설치함으로써 초기화 에러 해결
- `cv2.imshow` 코드의 위치를 5초마다 동작하는 메인 스레드에서 "0.1초마다 카메라만 계속 캡처하는 서브 스레드" 쪽으로 이관하여 쾌적한 30FPS UI 갱신 성능 고안

---

## 📅 2026-03-24

### 🚀 진행 내용
- `main` 환경 보호를 위해 나만의 독립적인 개발 공간(`dev_park` 브랜치) 개설
- 단일 스크립트(`rag_test.py`)로 짜여있던 코드를 협업이 가능하도록 전면 모듈화 (설정, RAG, Vision, Voice, GUI 등 폴더 분리)
- 내가 개발할 **Vision AI 모듈**(`vision/camera.py`)의 기본 구조(스켈레톤) 구성
- 가상 사진 입력을 통해 Vision AI 모조 분석 후 → RAG 서버 답변이 나오는 E2E 파이프라인(`main.py`로 통합) 모드 구축 및 정상 동작 확인

### 💥 발생한 문제 (Issue)
1. `main.py` 실행 타임에 패키지 누락(`ModuleNotFoundError: No module named 'langchain_community'`) 발생
2. Windows 환경 터미널에서 한국어와 특수문자(이모지)를 출력하다가 `cp949 UnicodeEncodeError` 앱 튕김 현상 발생
3. 지정한 AI 모델(`qwen2.5:1.5b`)이 로컬 환경에 없어 `ConnectionError / 404` 뱉음

### 💡 해결 및 배운 점 (Solution/TIL)
- `pip install langchain langchain-community langchain-core...` 등으로 필수 패키지들을 모두 설치 완료
- 스크립트 실행 전 Windows 환경 변수에 `$env:PYTHONIOENCODING="utf-8"`을 할당해주어 강제로 utf-8로 인코딩하도록 처리하여 에러 해결
- `ollama` CLI가 시스템 환경변수(PATH)에 잡혀있지 않았으나, 백그라운드 API를 직접 호출하여 모델(qwen2.5) 다운로드 해결

--- 

## 📅 2026-03-28

### 🚀 진행 내용
- `vision/camera.py` 스크립트 캡처 저장 기능 고도화
- 바탕화면/루트 폴더 지저분해짐 방지를 위해 전용 저장 구역(`vision/captures/`) 디렉토리 추가 및 자동 생성 로직 구현
- 동일한 파일명으로 덮어씌워지던 문제 해결 (캡처 시각 `YYYYMMDD_HHMMSS` 기반의 고유 파일명 부여 적용)
- 실행 시 발생한 `cv2` 모듈 누락 에러 해결 (프로젝트 전용 `.venv`에 `opencv-python` 설치 완료)
- `vision/fire_detector.py` 전면 개편: YOLOv8 딥러닝 기반 화재/연기 객체 인식 로직 연동
- 라즈베리파이용 '완전 오프라인(`ultralytics` 로컬 구동)' 모드와 PC 테스트용 'Roboflow API' 모드를 자동 스위칭하는 하이브리드 아키텍처 구축
- 깃허브 공개 저장소(150 Epoch 훈련)에서 가장 가벼운 YOLOv8n `best.pt` 가중치를 추출하여 `vision/models/fire_smoke.pt` 파일로 배치 완료
- 최종 형태인 Phase 3(라즈베리파이 CCTV 실시간 자동 감시망) 구현 및 AI 센서 퓨전 트리거 설계 문서(`CCTV_MIGRATION_PLAN.md`) 작성 완료

---

## 📅 2026-04-09
### 🚀 진행 내용
- 라즈베리파이 구동 최적화(발열 방지)를 위한 딥러닝 모델 경량화(양자화) 작업 착수.
- NCNN 라이브러리의 최신 Windows Python 환경 미지원 이슈로 인해, 범용성이 뛰어난 멀티플랫폼 구동 표준인 ONNX(FP16 반정밀도) 포맷을 우회 채택하여 변환 적용 성공.
- PC 벤치마크 테스트 진행: 한 장 추론 속도가 기존 112.6ms에서 **87.4ms**로 약 22% 단축된 것을 실측 완료. (추후 라즈베리파이 적용 시 200~300% 체감 향상 기대)

---

## 📅 [다음 주 목표 및 계획]
### 🚀 진행 예정 내용
- 라즈베리파이(Edge 디바이스) 환경으로 코드 이식 및 실제 카메라 모듈 연동 테스트
- 발열 및 성능 최적화를 위해 INT8, INT4 등 추가적인 양자화(Quantization) 모델 구동 풀 테스트
- 각 양자화 모델별 벤치마크(FPS 속도, 검출 정확도, 리소스 점유율)를 비교하여 엣지 세이버(라즈베리파이) 프로젝트에 가장 최적화된 최종 모델 선정

---

## 📅 [어렵지 않게 시작하는 다음 날]
### 🚀 진행 내용
- ...
---
*(새로운 날이 시작될 때마다 위에 템플릿을 복사해서 맨 위에 계속 추가해 주세요!)*
