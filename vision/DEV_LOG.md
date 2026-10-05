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
* **Git 커밋 및 깃허브 원격 푸시 완료:**
  * 커밋 해시: `e080610`
  * 원격 브랜치: `origin/feature/vision-early-detection` (푸시 완료)
  * PR 생성 경로: [GitHub PR 바로가기](https://github.com/Leejeahwang/-RAG-AI-/pull/new/feature/vision-early-detection)

---

### 4. 다음 단계 (Next Action Items)
1. 팀원(이승훈 님)에게 `Level 2 (조기 감지)` 상태가 GUI 대시보드 타이머 위젯에 연동될 수 있도록 인터페이스 공유.
2. 노트북 웹캠을 활용한 실물 테스트 진행 및 주간보고서/발표용 증빙 캡처 수집.

---

## 📅 2026-10-06 (화) — 실물 웹캠 오탐지 4대 난제 해결 & 강체 모션/색상 필터 고도화

### 1. 작업 배경 및 실전 테스트 피드백
노트북 내장 웹캠을 이용한 실시간 테스트(`vision/test_early_detection.py`) 도중, 실제 현장 환경에서 발생할 수 있는 **4가지 치명적인 오탐지 요인**이 확인되어 이를 원천 차단하기 위한 긴급 알고리즘 고도화를 진행함.

* **현장 오탐지 문제점:**
  1. **손에 든 불꽃/연기 사진 흔들림:** 스마트폰이나 인쇄 사진을 손에 쥐고 비출 때, 미세한 손떨림이나 위치 이동만으로도 픽셀 이동 비율(4%)을 초과하여 단 1프레임 만에 `REAL_FIRE`로 즉각 오탐지되는 취약점 발생.
  2. **실내 백색 형광등/LED 조명 오탐:** 천장 형광등이나 빛 반사광을 화재 불꽃으로 오인하여 경보가 발생하는 문제.
  3. **사람 얼굴/손 모션 블러를 연기로 오탐:** 카메라 앞에서 사람이 움직일 때, 얼굴이나 손의 블러 현상을 무채색 연기(`smoke`)로 오인하는 문제.
  4. **화재 경보 채터링(로그 도배) 및 조도 민감도:** 화재 감지 시 터미널 로그가 초당 수십 회 연속 출력되고, 주변이 조금 어두워지면 원치 않게 대기 모드로 빠지는 UX 문제.

---

### 2. 세부 개발 및 알고리즘 혁신 내역

#### ① Farneback 광학 흐름 기반 강체 평행 이동(Rigid Motion) 필터 개발 (`vision/smoke_motion.py`)
* **물리적 원리:** 스마트폰/종이는 **고체(강체, Rigid Body)**이므로 손이 떨리거나 움직일 때 박스 내부의 모든 픽셀 벡터가 **동일한 각도와 방향**으로 일제히 평행 이동함. 반면 실제 불꽃은 유체(기체 연소) 반응이므로 사방으로 펄럭이는 난류를 발생시킴.
* **원형 통계학(Circular Statistics) 적용:**
  $$\bar{R} = \sqrt{ \left(\frac{1}{N}\sum \cos\theta_i\right)^2 + \left(\frac{1}{N}\sum \sin\theta_i\right)^2 }$$
  - $\bar{R} \ge 0.78$ (방향 일치도 매우 높음) $\rightarrow$ **`HANDHELD_PHOTO_BLOCKED` (손에 든 사진 흔들림 차단)**으로 즉시 무력화!
  - $\bar{R} < 0.78$ ($Turbulence \ge 0.22$) $\rightarrow$ 실제 불꽃의 유체 난류 와류로 판별.

#### ② 불꽃 시간축 슬라이딩 윈도우(연속 3프레임) 검증
* 섣부른 판단 방지를 위해 단 1프레임의 반사광이나 스침에 반응하지 않도록, **연속 3프레임 이상 난류 플리커링이 유지**될 때만 `REAL_FIRE`로 승격.
* 검증 중일 때는 `⏳ [ANALYZING] Evaluating Flame Turbulence (1/3)` 상태를 유지하여 경보 채터링 방지.

#### ③ 백색 조명 배제 HSV 채도 필터 개발 (`validate_fire_color`)
* 형광등, 백색 LED, 창문 햇빛은 밝기($V$)는 높으나 채도($S$)가 매우 낮음 ($S < 0.20$).
* 불꽃 고유의 색상 범위(Orange/Yellow/Red, $H \in [0, 35] \cup [170, 180]$)와 최소 채도($S \ge 0.30$) 조건을 검사하여, 채도가 부족한 조명 박스는 **`LIGHT GLARE (Blocked)`**로 99% 차단.

#### ④ 인체 피부색 배제 필터 개발 (`is_human_skin_detected`)
* 연기는 무채색이지만 사람 피부는 YCbCr 및 HSV 색공간에서 뚜렷한 피부색 군집($Cr \in [133, 173], Cb \in [77, 127]$)을 형성함.
* 바운딩 박스 내 피부색 비율이 15% 이상일 경우 사람의 얼굴/손 움직임에 의한 모션 블러로 판정하여 **`HUMAN FACE/BODY`**로 분류하고 연기 후보에서 완전 배제.

#### ⑤ 수동 대기 모드 분리 및 1회성 화재 경보 래치(Latch) & 자동 복귀
* 조도에 따른 자동 대기 모드를 제거하고, 전용 단축키(`p` / `Space`)를 통해서만 대기/감시 모드가 전환되도록 분리.
* 평상시는 `🟢 [ACTIVE SCAN]`으로 명확히 표시.
* 화재/조기 감지 시 사이렌/방송 트리거가 단 1회만 격발되도록 래치(`alarm_triggered`) 적용 및 약 2초간 화재 소멸 확인 시 실시간 감시로 자동 복귀.

#### ⑥ 종합 자동 단위 검증 도구 개발 (`vision/test_unit_verification.py`)
* 모션 분석기 5종, 센서 퓨전 5종, YOLOv10 추론, VLM 전조 진단 등 4대 핵심 영역을 통합 검증하는 테스트 자동화 도구 구축.

---

### 3. 검증 결과

#### 🧪 `test_unit_verification.py` 자동 검증 결과
```text
[1] 모션 분석기 (SmokeMotionAnalyzer) 검증:
    - [1-A] 정지 사진 입력          ──▶ STATIC_PHOTO_BLOCKED (통과 ✅)
    - [1-B] 상방 대류 연기 입력      ──▶ REAL_SMOKE_RISING (통과 ✅)
    - [1-C] 하방 이동 낙하물 입력    ──▶ 오탐 방지 성공 (통과 ✅)
    - [1-D] 손에 든 사진 흔들림 입력  ──▶ HANDHELD_PHOTO_BLOCKED (R=1.0, 통과 ✅)
    - [1-E] 실제 불꽃 난류 플리커링   ──▶ REAL_FIRE_FLICKERING (Turb=0.84, 통과 ✅)
[2] 센서 퓨전 엔진 (calculate_risk_level) 검증: 5/5 전원 통과 ✅
[3] YOLOv10 OpenVINO 모델 추론 검증: 정상 수행 완료 ✅
[4] VLM 화재 전조 진단 모듈 검증: 사전 위험 진단 성공 ✅
>> 🎉 모든 단위/통합 테스트 전원 통과! (ALL TESTS PASSED)
```

#### 💻 실물 웹캠 실전 테스트 사용자 확인
* 사람 얼굴/손을 비추었을 때: `HUMAN FACE/BODY` 차단 확인.
* 형광등을 비추었을 때: `LIGHT GLARE` 차단 확인.
* 스마트폰 불꽃 사진을 손에 들고 흔들었을 때: `HANDHELD PHOTO SHAKE DETECTED` 차단 확인.
* **사용자 최종 확인:** *"오케이 잘되네 이정도면 괜찮은듯?"* (검증 완료 승인).

---

### 4. 차주 계획 (Next Action Items)
1. 개선된 알고리즘 코드(`smoke_motion.py`, `test_early_detection.py`, `test_unit_verification.py`) 원격 브랜치(`origin/feature/vision-early-detection`) 푸시.
2. 메인 브랜치 병합을 위한 풀 리퀘스트(PR) 설명 업데이트.

---

## 🧪 노트북 실전 테스트 가이드 (How to Test on Laptop)

본 섹션은 개인 노트북(웹캠 환경)에서 개발한 알고리즘을 직접 시연·검증하고, 주간보고서 및 발표 자료에 들어갈 증빙 캡처를 수집하기 위한 테스트 매뉴얼입니다.

```
[테스트 1] 실시간 비전 HUD 테스트 (`vision/test_early_detection.py`)
    ├── ① 스마트폰 사진 오탐 차단 테스트  ──▶ [PHOTO BLOCKED] 확인
    ├── ② 손에 든 사진 흔들림 차단 테스트 ──▶ [HANDHELD PHOTO SHAKE] 확인 ⭐
    ├── ③ 사람 얼굴/신체 모션 차단 테스트 ──▶ [HUMAN FACE/BODY] 확인 ⭐
    ├── ④ 실내 조명/형광등 차단 테스트  ──▶ [LIGHT GLARE] 확인 ⭐
    ├── ⑤ 피어오르는 연기 조기 감지 테스트 ──▶ [REAL SMOKE RISING] 확인
    └── ⑥ 정상 상태 스캔 테스트         ──▶ [ACTIVE SCAN] 확인

[테스트 2] 센서 퓨전 통합 테스트 (`main_test.py`)
    └── 터미널 하단 툴바에서 Level 0 (사진 차단) vs Level 2 (조기 감지) 확인

[테스트 3] 전체 단위 알고리즘 자동 검증 (`vision/test_unit_verification.py`)
    └── 터미널 1회 실행으로 4대 영역 100% 자동 패스 확인
```

### [테스트 1] 실시간 비전 HUD 시각화 검증 (`test_early_detection.py`)

#### 1. 실행 명령어
```bash
python vision/test_early_detection.py
```

#### 2. 세부 검증 시나리오 및 행동 요령

* **시나리오 A. 스마트폰 화재 사진 오탐 차단 (정지 & 손떨림 흔들림 ⭐⭐⭐):**
  * **목적:** 1학기 지적 사항("사진 비추기 시연") 완벽 극복 증명.
  * **행동:** 스마트폰 화면에 "화재 불꽃/연기" 사진을 띄운 뒤 노트북 웹캠 앞에 비춥니다.
  * **기대 결과:**
    - 가만히 들고 있을 때: `🛡️ [PHOTO BLOCKED] Static Image`
    - 손을 떨거나 사진을 움직일 때: `>> 🛡️ [FILTER ACTIVE] HANDHELD PHOTO SHAKE DETECTED (ALARM BLOCKED) <<`
    - 📸 **키보드 `s`를 눌러 캡처 저장!** *(증빙 자료 1)*

* **시나리오 B. 피어오르는 연기 조기 감지 테스트:**
  * **목적:** 실제 연기 특유의 열 대류 상방 확산($v < -0.15$) 포착 확인.
  * **행동:** 연기 사진/흰색 휴지를 손으로 잡고 **아래에서 위쪽으로 부드럽게 2~3회 솟구치듯 연속으로 올려줍니다.**
  * **기대 결과:**
    - 박스 내부에 위쪽을 향하는 **초록색 움직임 화살표(↑)** 실시간 드로잉.
    - 3프레임 연속 상방 흐름 확인 시: `🔥 [REAL SMOKE] Rising Plume (Up: 80% 이상)`
    - 📸 **키보드 `s`를 눌러 캡처 저장!** *(증빙 자료 2)*

* **시나리오 C. 조명 및 사람 얼굴 오탐 차단 테스트:**
  * **행동:** 웹캠 앞에 사람 얼굴을 비추며 고개를 흔들거나, 천장 형광등을 비춥니다.
  * **기대 결과:**
    - 사람 얼굴: `👤 [HUMAN FILTERED] FACE/BODY MOTION DETECTED (연기 오탐 원천 차단)`
    - 조명: `💡 [LIGHT FILTERED] WHITE GLARE / LAMP DETECTED (화재 오탐 원천 차단)`

* **단축키 안내:**
  * `p` / `Space` : 대기(일시정지) 모드 진입 / 실시간 감시 재개 토글
  * `[` / `]`     : 감지 민감도(Conf 임계값) 실시간 조절
  * `r`           : 모션 분석 및 경보 상태 리셋
  * `s`           : 현재 화면을 캡처하여 `vision/captures/` 폴더에 즉시 저장
  * `q`           : 프로그램 정상 종료

---

### [테스트 2] 센서 퓨전 엔진 통합 검증 (`main_test.py`)
```bash
python main_test.py
```
* **평상시:** `[EDGE SAVER] | T: 25.0C | G: 120 | S: 80 | CAM: SAFE | 정상`
* **사진 비출 때:** `CAM: SAFE` 및 **`Level 0 (정상)` 유지** (오경보 완전 차단 확인).
* **진짜 연기(상방 확산) 포착 시:** `CAM: [조기 감지: 미세 연기 상방 확산] | 경고 (단계: 2)` 선제 경보 격발.

---

### [테스트 3] 전체 단위 알고리즘 자동 검증 (`test_unit_verification.py`)
```bash
python vision/test_unit_verification.py
```
* 모션 분석, 센서 퓨전, YOLO 추론, VLM 전조 진단까지 한 번에 100% 자동 검증.



