# 📝 Vision AI 모듈 개발 일지 (박규태)

본 문서는 **엣지 세이버(Edge Saver)** 프로젝트의 **Vision AI 및 센서 퓨전** 파트 담당자(박규태)의 일일 작업 내역, 알고리즘 개선 과정, 테스트 결과 및 향후 계획을 기록하는 개발 로그입니다.

---

## 📅 2026-10-02 (금) — 비전 조기 감지 & 사진 오탐 차단 엔진 착수

### 1. 작업 배경 및 목표
* **1학기 평가 피드백 분석:**
  * *"센서에 감지될 때는 이미 화재가 커진 상태인데 무슨 의미가 있는가?"* $\rightarrow$ 불꽃이 터지기 전 훈소(Smoldering) 단계의 **미세 연기 조기 감지(Pre-fire Early Detection)** 필요성 대두.
  * *"모니터/스마트폰에 화재 사진을 띄워 웹캠에 비추는 단편적인 시연"* $\rightarrow$ 정지 사진과 실제 움직이는 연기를 구별하는 **동역학적 모션 검증 체계** 필수.
* **작업 목표:**
  * 2학기 고도화 개발을 위한 전용 기능 브랜치(`feature/vision-early-detection`) 분기.
  * OpenCV Optical Flow 기반 연기 상방 확산 검증 및 정지 사진 오탐 차단 프로토타입 구현.
  * 실시간 웹캠 HUD 시각화 테스트 도구 제작.

---

### 2. 세부 개발 내역

#### ① 신규 브랜치 생성 및 환경 검증
* 브랜치명: `feature/vision-early-detection`
* OpenCV 4.10.0, Ultralytics 8.4.22, PyTorch 가속 환경 및 모델 가중치(`fire_smoke.pt`, `YOLOv10-FireSmoke-M.pt`) 로드 경로 점검 완료.

#### ② 연기 동역학 분석 모듈 개발 (`vision/smoke_motion.py`)
* **핵심 기능:**
  1. **정지 사진 오탐 원천 차단 (`STATIC_PHOTO_BLOCKED`):**
     * YOLO가 `smoke`를 감지하더라도, 바운딩 박스 내부의 움직임 픽셀 비율이 기준치(4%) 미만인 경우 스마트폰/인쇄 사진으로 판정하여 오경보 차단.
  2. **상방 대류(Upward Diffusion) 벡터 분석:**
     * Farneback Dense Optical Flow를 사용하여 연기 픽셀의 이동 속도 벡터($u, v$) 계산.
     * 이미지 좌표계 기준 위쪽 방향($v < -0.15$)으로 향하는 픽셀 비율(`upward_ratio`) 산출.
  3. **시간축 슬라이딩 윈도우 스코어링:**
     * 연기 특유의 난류 와류(Vortex/Eddy)로 인한 순간 흔들림을 보정하기 위해 최근 프레임 윈도우(`deque`) 기반으로 연속 상방 대류 감지 시 `REAL_SMOKE_RISING` 확정.
  4. **시각화 오버레이 (`draw_motion_overlay`):**
     * 바운딩 박스 내부 픽셀의 이동 방향을 나타내는 화살표 벡터 실시간 렌더링.

#### ③ 실시간 시각화 테스트 도구 개발 (`vision/test_early_detection.py`)
* 웹캠(`cv2.VideoCapture(0)`) 및 동영상 파일 소스 지원.
* 화면 상단 반투명 HUD를 통해 FPS, 감지 객체 및 판정 상태 표시:
  * `>> 🚨 [CONFIRMED] RISING SMOKE PLUME (EARLY DETECTION ACTIVE) <<`
  * `>> 🛡️ [FILTER ACTIVE] STATIC PHOTO DETECTED (ALARM BLOCKED) <<`
* 캡처 단축키(`s`), 상태 리셋(`r`), 종료(`q`) 인터랙션 지원.

---

### 3. 검증 및 테스트 결과
* **합성 프레임 단위 테스트 통과:**
  * 동일 정지 프레임 입력 $\rightarrow$ `STATIC_PHOTO_BLOCKED` 판정 (정상 동작)
  * 상방 이동 패치 입력 $\rightarrow$ `upward_ratio` 80% 이상 기록 및 `REAL_SMOKE_RISING` 정상 확정
* **Git 커밋 완료:**
  * 커밋 해시: `492d19e`
  * 커밋 메시지: `feat(vision): add smoke motion analyzer with optical flow and test tool`

---

### 4. 차주 계획 (Next Action Items)
1. 실물 웹캠 및 다양한 연무 환경(가습기, 연기 스프레이 등)에서의 모션 임계값(`min_motion_mag`, `upward_ratio_threshold`) 정밀 튜닝.
2. 클라우드 VLM API(GPT-4o-mini / Gemini Flash) 연동을 통한 화재 전조 상황(전열기 무인 방치 등) 인지 모듈(`vision/vlm_analyzer.py`) 기초 설계.

---

## 📅 2026-10-05 (월) — 비전 모션 통합, 센서 퓨전 엔진 개편 및 클라우드 VLM 모듈 개발

### 1. 작업 배경 및 목표
* 비전 단독 테스트(`test_early_detection.py`)로 검증된 모션 분석기를 기존 메인 파이프라인(`vision/fire_detector.py`, `sensors/fusion.py`, `main.py`)에 정식 통합.
* 센서가 울리기 전 비전 조기 감지 신호(`Level 2`) 및 사진 오탐 차단 신호(`Level 0`)를 시스템 전체에 반영.
* 평상시 온라인 환경에서 화재 전조 위험을 진단하는 클라우드 VLM 연동 모듈(`vision/vlm_analyzer.py`) 프로토타입 구현.

---

### 2. 세부 개발 내역

#### ① `vision/fire_detector.py` 모션 분석기 통합
* `detect_fire()` 내부에 `SmokeMotionAnalyzer`를 결합하여 감지된 연기/불꽃 박스의 모션 연속 검증 수행.
* **정지 사진 감지 시:** `is_static_photo=True`, `fire_detected=False`로 오경보를 사전 무력화.
* **미세 연기 상방 확산 감지 시:** `is_real_smoke=True`, `description`에 조기 감지 태그 부여.

#### ② 센서 퓨전 엔진 개편 (`sensors/fusion.py`)
* 비전 분석 결과 딕셔너리를 받아 세분화된 위험도 산정:
  * **사진 오탐 시:** `Level 0 (정상)` 유지 (오경보 차단).
  * **미세 훈소 연기 조기 감지 시 (센서 수치 0일 때):** `Level 2 (경고: 비전 초기 훈소 연기 조기 포착!)` 선제 발령.
  * **화재 전조 위험 감지 시 (VLM):** `Level 1 (주의: 화재 전조 주의)` 발령.
  * 기존 boolean 인자(`fire_detected_by_camera`)와 100% 하위 호환성 유지.

#### ③ 클라우드 VLM 화재 전조 진단 모듈 개발 (`vision/vlm_analyzer.py`)
* OpenAI `gpt-4o-mini` API 연동을 통해 CCTV 영상의 환경적 화재 전조(전열기 무인 방치, 배전반 앞 가연물 적치 등) 진단 구조 설계.
* 네트워크 단절 및 API 키 부재 시 안전하게 폴백하는 방어 로직과 시연/테스트용 모의 함수(`simulate_hazard`) 구현.

#### ④ 메인 시스템 (`main.py`, `main_test.py`) 연동
* 비전 분석 상세 객체를 퓨전 엔진으로 직결 전달하도록 파이프라인 갱신.

---

### 3. 검증 결과
* 단위 테스트 4종 전원 통과:
  1. 사진 오탐 차단: `Level 0 정상` (성공)
  2. 비전 미세 연기 조기 감지 (센서 0일 때): `Level 2 경고 | early: True` (성공)
  3. 클라우드 VLM 전열기 방치 진단: `Level 1 주의 | early: True` (성공)
  4. 기존 레거시 호출 호환성: `Level 2 경고` (성공)

---

### 4. 다음 단계 (Next Action Items)
1. 팀원(이승훈 님)에게 `Level 2 (조기 감지)` 상태가 GUI 대시보드 타이머 위젯에 연동될 수 있도록 인터페이스 공유.
2. 실제 웹캠 환경에서 전열기 방치 및 연무 발생 모의 시연 테스트 진행.

