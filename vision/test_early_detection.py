"""
vision/test_early_detection.py - 비전 조기 감지 & 사진 오탐 차단 실시간 시각화 테스트 도구
========================================================================================
작성자: 박규태 (Vision AI 담당)
용도:
  - 웹캠이나 테스트 영상을 통해 YOLO + Optical Flow 결합 알고리즘을 실시간으로 확인
  - 스마트폰으로 불/연기 사진을 비췄을 때 [PHOTO BLOCKED]가 뜨는지 테스트
  - 실제 가습기/연무나 라이터 불꽃에서 [REAL SMOKE]가 뜨는지 테스트

실행 방법:
  python vision/test_early_detection.py
  (또는 비디오 파일 테스트: python vision/test_early_detection.py --source path/to/video.mp4)
"""

import os
import sys
import time
import argparse
import cv2
import numpy as np

# 프로젝트 루트 경로 추가
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ultralytics import YOLO
from vision.smoke_motion import SmokeMotionAnalyzer, MotionAnalysisResult

# 지원하는 모델 목록 (인식률이 높은 최신 모델 우선 탐색)
MODEL_DIR = os.path.join(ROOT_DIR, "vision", "models")
POSSIBLE_MODELS = [
    os.path.join(MODEL_DIR, "YOLOv10-FireSmoke-M_int8_openvino_model"),
    os.path.join(MODEL_DIR, "YOLOv10-FireSmoke-M.pt"),
    os.path.join(MODEL_DIR, "fire_smoke.pt"),
    os.path.join(MODEL_DIR, "best_nano_111.pt"),
    os.path.join(MODEL_DIR, "fire_smoke.onnx")
]

def validate_fire_color(frame: np.ndarray, bbox: tuple, min_fire_ratio: float = 0.10) -> tuple:
    """
    형광등, 백색 LED, 창문 빛 등의 무채색 고명도 조명을 불꽃 오탐에서 원천 차단합니다.
    불꽃 특유의 적색/주황색/황색 색조(Hue) 및 높은 채도(Saturation)를 검사합니다.
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if (x2 - x1) < 10 or (y2 - y1) < 10:
        return False, 0.0

    roi = frame[y1:y2, x1:x2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # 불꽃 색상 범위:
    # 1. 빨간색 (Hue 0~10 및 160~180, 채도 S > 65, 명도 V > 80)
    # 2. 주황/노랑 (Hue 11~35, 채도 S > 60, 명도 V > 90)
    mask_red1 = cv2.inRange(hsv, np.array([0, 65, 80]), np.array([10, 255, 255]))
    mask_red2 = cv2.inRange(hsv, np.array([160, 65, 80]), np.array([180, 255, 255]))
    mask_yellow = cv2.inRange(hsv, np.array([11, 60, 90]), np.array([35, 255, 255]))
    
    fire_mask = mask_red1 | mask_red2 | mask_yellow
    fire_pixel_count = np.sum(fire_mask > 0)
    fire_ratio = float(fire_pixel_count) / float(fire_mask.size + 1e-6)

    # 형광등이나 백색광은 채도(Saturation)가 매우 낮아 fire_ratio가 거의 0%임!
    is_valid = fire_ratio >= min_fire_ratio
    return is_valid, fire_ratio

def is_human_skin_detected(frame: np.ndarray, bbox: tuple, min_skin_ratio: float = 0.16) -> tuple:
    """
    YCrCb 및 HSV 색공간을 분석하여 사람의 피부(얼굴/손/목)를 감지합니다.
    연기는 무채색이므로 피부색 비율이 0~3%에 불과한 반면, 사람 얼굴은 20~60% 이상을 차지합니다.
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if (x2 - x1) < 15 or (y2 - y1) < 15:
        return False, 0.0

    roi = frame[y1:y2, x1:x2]
    
    # 1. YCrCb 색공간 기반 피부색 검출 (조도 변화에 강인)
    ycrcb = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb)
    skin_ycrcb = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
    
    # 2. HSV 색공간 보조 검출 (Hue 0~25 살색 영역)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    skin_hsv = cv2.inRange(hsv, np.array([0, 35, 60]), np.array([25, 180, 255]))
    
    # 두 조건 결합
    combined_skin = cv2.bitwise_and(skin_ycrcb, skin_hsv)
    skin_pixel_count = np.sum(combined_skin > 0)
    skin_ratio = float(skin_pixel_count) / float(combined_skin.size + 1e-6)
    
    is_skin = skin_ratio >= min_skin_ratio
    return is_skin, skin_ratio

def load_yolo_model():
    """사용 가능한 YOLO 가중치 자동 로드"""
    for path in POSSIBLE_MODELS:
        if os.path.exists(path):
            print(f"✅ [YOLO] 모델 로드 성공: {os.path.basename(path)}")
            return YOLO(path)
    raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다. {MODEL_DIR} 폴더를 확인하세요.")

def main():
    parser = argparse.ArgumentParser(description="비전 조기 감지 및 사진 오탐 차단 테스트")
    parser.add_argument("--source", type=str, default="0", help="카메라 번호 (기본: 0) 또는 비디오 파일 경로")
    parser.add_argument("--conf", type=float, default=0.35, help="YOLO 감지 확신도 임계값 (기본: 0.35)")
    args = parser.parse_args()

    # 1. 모델 및 모션 분석기 초기화
    print("\n" + "=" * 60)
    print("🔥 엣지 세이버 — 비전 조기 감지 & 사진 오탐 차단 실시간 테스트 🔥")
    print("=" * 60)
    
    model = load_yolo_model()
    # 찰나의 몸짓/고개 끄덕임 오탐 방지를 위해 연속 상방 프레임을 5프레임으로 강화
    analyzer = SmokeMotionAnalyzer(
        min_motion_mag=0.45,
        static_motion_ratio=0.04,
        upward_ratio_threshold=0.52,
        required_consecutive_frames=5
    )

    # 2. 카메라 또는 비디오 소스 열기
    src = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    
    if not cap.isOpened():
        print(f"❌ [에러] 영상 소스({args.source})를 열 수 없습니다.")
        return

    print("\n👉 조작 키 안내:")
    print("   [p] / [Space] : 대기(일시정지) 모드 진입/해제 (수동 전환)")
    print("   [ [ ] / [ ] ] : 감지 민감도 실시간 조절 (현재 임계값 낮춤/높임)")
    print("   [r]           : 모션 분석 및 경보 상태 리셋")
    print("   [s]           : 현재 화면 캡처 저장")
    print("   [q]           : 프로그램 종료\n")

    current_conf = args.conf
    prev_time = time.time()
    fps = 0.0
    last_term_log = 0.0
    prev_term_status = ""
    alarm_triggered = False
    safe_counter = 0
    is_paused = False  # 수동 대기(일시정지) 모드 플래그

    while True:
        ret, frame = cap.read()
        if not ret:
            print("영상 재생이 끝나거나 프레임을 읽지 못했습니다.")
            break

        # FPS 계산
        curr_time = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(1e-4, curr_time - prev_time))
        prev_time = curr_time

        display_frame = frame.copy()
        h, w = frame.shape[:2]

        # 수동 대기 모드인 경우 AI 추론을 멈추고 대기 화면 표시
        if is_paused:
            # 상단 HUD 대기 배너 표시
            hud_bg = display_frame[:70, :].copy()
            cv2.rectangle(display_frame, (0, 0), (w, 70), (40, 40, 40), -1)
            cv2.addWeighted(display_frame[:70, :], 0.75, hud_bg, 0.25, 0, display_frame[:70, :])
            cv2.putText(display_frame, "EDGE SAVER - SYSTEM ON STANDBY (PAUSED)", (15, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
            cv2.putText(display_frame, ">> ⏸️ [STANDBY MODE] DETECTION PAUSED (PRESS 'P' OR SPACE TO RESUME)", (15, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 215, 255), 2)
            
            cv2.imshow("Edge Saver Early Detection Tester", display_frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('p'), ord(' ')):
                is_paused = False
                prev_term_status = ""
                print("\n▶️ [감시 재개] 대기 모드가 해제되었습니다. 실시간 화재/연기 감시를 재개합니다.")
            elif key == ord('q'):
                print("\n🛑 테스트 프로그램을 종료합니다.")
                break
            continue

        # 평균 화면 밝기(조도) 계산
        gray_check = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray_check))
        is_low_light = mean_brightness < 30.0

        # 3. YOLO 추론 (verbose=False로 콘솔 로그 방지)
        results = model.predict(source=frame, conf=current_conf, save=False, verbose=False)
        boxes = results[0].boxes if len(results) > 0 else []

        smoke_boxes = []
        fire_boxes = []
        light_boxes = []   # 조명/빛 반사로 판정되어 차단된 박스들
        person_boxes = []  # 사람 얼굴/피부로 판정되어 차단된 박스들

        if len(boxes) > 0:
            names = results[0].names
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = str(names[cls_id]).lower()
                conf_val = float(box.conf[0])
                coords = [int(v) for v in box.xyxy[0]]
                box_w = coords[2] - coords[0]
                box_h = coords[3] - coords[1]

                # ① 최소 크기 필터 (너무 작은 먼지/노이즈 박스 원천 차단)
                if box_w < 30 or box_h < 30:
                    continue

                if "smoke" in cls_name:
                    # 🧑 사람 얼굴/피부 검증 (연기는 무채색이지만 사람은 피부색을 가짐)
                    is_skin, skin_ratio = is_human_skin_detected(frame, coords, min_skin_ratio=0.15)
                    if is_skin:
                        # 사람 얼굴/손 움직임에 의한 모션 블러로 판명 -> 연기 후보에서 배제!
                        person_boxes.append((coords, conf_val, skin_ratio))
                    elif conf_val >= max(0.35, current_conf):
                        smoke_boxes.append((coords, conf_val))
                elif "fire" in cls_name:
                    # 💡 HSV 불꽃 색상 & 채도 검증 (형광등, 백색 LED, 창문 빛 오탐 원천 차단!)
                    is_valid_fire, fire_ratio = validate_fire_color(frame, coords, min_fire_ratio=0.10)
                    if is_valid_fire and conf_val >= max(0.28, current_conf):
                        fire_boxes.append((coords, conf_val, fire_ratio))
                    else:
                        # 채도가 너무 낮아 백색 조명/빛 반사로 판별됨
                        light_boxes.append((coords, conf_val, fire_ratio))

        # 4. 모션 분석 및 시각화
        has_real_smoke = False
        has_real_fire = False
        has_static_photo = False
        has_rigid_photo = False
        has_evaluating_motion = False
        has_light_glare = False
        has_person = False
        target_class_desc = ""

        # 조명 오탐 박스 화면 시각화 (하늘색 박스)
        for coords, conf_val, f_ratio in light_boxes:
            x1, y1, x2, y2 = coords
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), (255, 200, 0), 2)
            cv2.putText(display_frame, f"LIGHT GLARE (Blocked {conf_val*100:.0f}%)", (x1, max(20, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 2)

        # 사람 감지 오탐 차단 박스 화면 시각화 (연두색 박스)
        for coords, conf_val, s_ratio in person_boxes:
            x1, y1, x2, y2 = coords
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 128), 2)
            cv2.putText(display_frame, f"HUMAN FACE/BODY ({conf_val*100:.0f}%)", (x1, max(20, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 128), 2)

        if smoke_boxes:
            # 가장 큰 연기 박스를 우선 분석
            smoke_boxes.sort(key=lambda b: (b[0][2] - b[0][0]) * (b[0][3] - b[0][1]), reverse=True)
            main_coords, conf_val = smoke_boxes[0]
            target_class_desc = f"SMOKE ({conf_val*100:.1f}%)"

            # 모션 분석 수행 (Farneback Optical Flow)
            motion_res = analyzer.analyze(frame, main_coords, class_name="smoke")
            display_frame = analyzer.draw_motion_overlay(display_frame, motion_res)

            if motion_res.is_real_smoke:
                has_real_smoke = True
            elif motion_res.is_static_photo:
                has_static_photo = True
                if motion_res.is_rigid_motion:
                    has_rigid_photo = True
            else:
                has_evaluating_motion = True

        elif fire_boxes:
            # 불꽃 박스에 대해서도 스마트폰/인쇄 사진 오탐 차단 분석 수행
            fire_boxes.sort(key=lambda b: (b[0][2] - b[0][0]) * (b[0][3] - b[0][1]), reverse=True)
            main_coords, conf_val, fire_ratio = fire_boxes[0]
            target_class_desc = f"FIRE ({conf_val*100:.1f}%)"

            # 모션 분석 수행 (손에 든 사진의 흔들림 vs 실제 불꽃 플리커링 난류)
            motion_res = analyzer.analyze(frame, main_coords, class_name="fire")
            display_frame = analyzer.draw_motion_overlay(display_frame, motion_res)

            if motion_res.is_real_fire:
                has_real_fire = True
            elif motion_res.is_static_photo:
                has_static_photo = True
                if motion_res.is_rigid_motion:
                    has_rigid_photo = True
            else:
                has_evaluating_motion = True

        elif person_boxes:
            has_person = True
            target_class_desc = f"HUMAN ({person_boxes[0][1]*100:.1f}%)"
        elif light_boxes:
            has_light_glare = True
            target_class_desc = f"WHITE_LIGHT ({light_boxes[0][1]*100:.1f}%)"
        else:
            # 감지 객체가 없으면 모션 버퍼 리셋
            analyzer.reset()

        # 5. 상단 HUD 정보창 렌더링
        hud_bg = display_frame[:70, :].copy()
        cv2.rectangle(display_frame, (0, 0), (w, 70), (20, 20, 20), -1)
        cv2.addWeighted(display_frame[:70, :], 0.75, hud_bg, 0.25, 0, display_frame[:70, :])

        # 시스템 타이틀 & FPS & 현재 Conf 임계값
        cv2.putText(display_frame, "EDGE SAVER - PRE-FIRE EARLY DETECTION TEST", (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.putText(display_frame, f"FPS: {fps:.1f} | CONF: {current_conf:.2f}", (w - 230, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

        # 조기 감지 판정 상태 표시
        if has_real_smoke:
            status_banner = ">> 🚨 [CONFIRMED] RISING SMOKE PLUME (EARLY DETECTION ACTIVE) <<"
            banner_color = (0, 0, 255) # 빨간색
            current_status = "REAL_SMOKE"
        elif has_real_fire:
            status_banner = ">> 🔥 [CONFIRMED] ACTIVE FLAME DETECTED (FIRE ALARM) <<"
            banner_color = (0, 0, 255) # 빨간색
            current_status = "REAL_FIRE"
        elif has_rigid_photo:
            status_banner = ">> 🛡️ [FILTER ACTIVE] HANDHELD PHOTO SHAKE DETECTED (ALARM BLOCKED) <<"
            banner_color = (255, 140, 0) # 주황색
            current_status = "HANDHELD_PHOTO_BLOCKED"
        elif has_static_photo:
            status_banner = ">> 🛡️ [FILTER ACTIVE] STATIC PHOTO DETECTED (ALARM BLOCKED) <<"
            banner_color = (255, 140, 0) # 주황색
            current_status = "PHOTO_BLOCKED"
        elif has_evaluating_motion:
            status_banner = ">> ⏳ [ANALYZING] EVALUATING FLAME TURBULENCE / MOTION VECTORS..."
            banner_color = (0, 255, 255) # 노란색
            current_status = "ANALYZING"
        elif has_person:
            status_banner = ">> 👤 [HUMAN FILTERED] FACE/BODY MOTION DETECTED (ALARM BLOCKED) <<"
            banner_color = (0, 255, 128) # 연두색
            current_status = "HUMAN_BLOCKED"
        elif has_light_glare:
            status_banner = ">> 💡 [LIGHT FILTERED] WHITE GLARE / LAMP DETECTED (ALARM BLOCKED) <<"
            banner_color = (255, 200, 0) # 하늘색
            current_status = "LIGHT_BLOCKED"
        else:
            status_banner = ">> 🟢 [ACTIVE SCAN] REAL-TIME MONITORING - AREA SAFE (실시간 감시 중)..."
            banner_color = (0, 220, 0) # 연초록색
            current_status = "SCANNING"

        cv2.putText(display_frame, status_banner, (15, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, banner_color, 2)

        # 조도가 너무 낮을 때 안내 배너
        if is_low_light:
            cv2.putText(display_frame, "⚠️ [LOW LIGHT] CAMERA TOO DARK OR BLOCKED (화면 어두움 - 거리/조명 확인)",
                        (15, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)

        # 6. 터미널 실행창 실시간 상태 출력 (1회성 화재 경보 격발 및 채터링 방지)
        if current_status in ("REAL_FIRE", "REAL_SMOKE"):
            safe_counter = 0
            if not alarm_triggered:
                alarm_triggered = True
                prev_term_status = current_status
                print("\n" + "=" * 65)
                if current_status == "REAL_FIRE":
                    print(f"🚨 [화재 경보 1회 격발] {target_class_desc} 실제 불꽃 감지 확정!")
                    print("📢 [기존 시스템 연동 동작] 비상 사이렌 및 화재 대피 음성 방송 송출 트리거 발생!")
                else:
                    print(f"🚨 [비전 조기 감지 1회 격발] {target_class_desc} 피어오르는 미세 연기 확정!")
                    print("📢 [기존 시스템 연동 동작] 센서 도달 전 조기 주의 음성 및 관제실 선제 알림 발생!")
                print("💡 (현재 경보 상태 유지 중 | 'r' 키를 누르면 즉시 리셋되어 다시 테스트 가능)")
                print("=" * 65 + "\n")
        elif current_status in ("PHOTO_BLOCKED", "HANDHELD_PHOTO_BLOCKED"):
            safe_counter = 0
            if current_status != prev_term_status:
                prev_term_status = current_status
                if current_status == "HANDHELD_PHOTO_BLOCKED":
                    print(f"[실행창 HUD] 🛡️ [사진 흔들림 차단] {target_class_desc} 감지됨 | 손에 든 사진(강체 평행 이동) 판정으로 알람 무력화 (Level 0 유지)")
                else:
                    print(f"[실행창 HUD] 🛡️ [정지 사진 차단] {target_class_desc} 감지됨 | 고정 사진 판정으로 알람 무력화 (Level 0 유지)")
        elif current_status == "HUMAN_BLOCKED":
            safe_counter = 0
            if current_status != prev_term_status:
                prev_term_status = current_status
                print(f"[실행창 HUD] 👤 [사람 감지 필터] {target_class_desc} 사람 얼굴/피부 모션 감지 (연기 오탐 차단)")
        elif current_status == "LIGHT_BLOCKED":
            safe_counter = 0
            if current_status != prev_term_status:
                prev_term_status = current_status
                print(f"[실행창 HUD] 💡 [조명 오탐 차단] {target_class_desc} 백색광/형광등 감지 (채도 부족) -> 화재 경보 차단")
        elif current_status == "SCANNING":
            if alarm_triggered:
                safe_counter += 1
                if safe_counter >= 30:  # 약 1.5~2초간 화재가 완전히 사라지면 자동 해제
                    alarm_triggered = False
                    safe_counter = 0
                    prev_term_status = "SCANNING"
                    print("[실행창 HUD] 🟢 [상황 해제] 화재 징후 소멸 -> 실시간 감시 모드로 복귀했습니다.\n")
            elif current_status != prev_term_status:
                prev_term_status = current_status
                print(f"[실행창 HUD] 🟢 [실시간 감시 중] 이상 징후 없음 (스캔 가동 중... FPS: {fps:.1f} | CONF: {current_conf:.2f})")
        elif current_status == "ANALYZING":
            if current_status != prev_term_status and not alarm_triggered:
                prev_term_status = current_status
                print(f"[실행창 HUD] ⏳ [동역학 분석 중] {target_class_desc} 모션 벡터 검증 진행 중...")

        # 7. 화면 출력
        cv2.imshow("Edge Saver Early Detection Tester", display_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("\n🛑 테스트 프로그램을 종료합니다.")
            break
        elif key in (ord('p'), ord(' ')):
            is_paused = True
            print("\n⏸️ [수동 대기 모드 진입] 감시가 일시 정지되었습니다. ('p' 또는 Space 키를 누르면 재개)")
        elif key == ord('['):
            current_conf = max(0.10, round(current_conf - 0.05, 2))
            print(f"🔧 [민감도 조절] 탐지 임계값 낮춤(민감하게 탐지): CONF = {current_conf:.2f}")
        elif key == ord(']'):
            current_conf = min(0.70, round(current_conf + 0.05, 2))
            print(f"🔧 [민감도 조절] 탐지 임계값 높임(오탐 원천 억제): CONF = {current_conf:.2f}")
        elif key == ord('r'):
            analyzer.reset()
            alarm_triggered = False
            safe_counter = 0
            prev_term_status = ""
            print("🔄 [리셋] 화재 경보 및 모션 분석기가 초기화되었습니다. 다시 테스트 가능합니다.")
        elif key == ord('s'):
            save_dir = os.path.join(ROOT_DIR, "vision", "captures")
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f"test_capture_{int(time.time())}.jpg")
            cv2.imwrite(save_path, display_frame)
            print(f"📸 현재 화면이 저장되었습니다: {save_path}")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
