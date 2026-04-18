# 📓 Vision AI 개발 일지 (박규태)

이 문서는 엣지 세이버의 **Vision AI 모듈(`vision/camera.py` 등)**을 개발하면서 발생한 진행 상황, 문제점, 그리고 해결 방법을 매일 기록하는 용도입니다. 
(이 내용들이 쌓이면 주간 보고서 작성 시 그대로 복사해서 붙여넣을 수 있습니다.)

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

## 📅 [어제 날짜]
### 🚀 진행 내용
- ...
---
*(새로운 날이 시작될 때마다 위에 템플릿을 복사해서 맨 위에 계속 추가해 주세요!)*
