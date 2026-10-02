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

# 지원하는 모델 목록 (가장 가벼운 모델 우선 탐색)
MODEL_DIR = os.path.join(ROOT_DIR, "vision", "models")
POSSIBLE_MODELS = [
    os.path.join(MODEL_DIR, "fire_smoke.pt"),
    os.path.join(MODEL_DIR, "YOLOv10-FireSmoke-M.pt"),
    os.path.join(MODEL_DIR, "best_nano_111.pt"),
    os.path.join(MODEL_DIR, "fire_smoke.onnx")
]

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
    parser.add_argument("--conf", type=float, default=0.25, help="YOLO 감지 확신도 임계값 (기본: 0.25)")
    args = parser.parse_args()

    # 1. 모델 및 모션 분석기 초기화
    print("\n" + "=" * 60)
    print("🔥 엣지 세이버 — 비전 조기 감지 & 사진 오탐 차단 실시간 테스트 🔥")
    print("=" * 60)
    
    model = load_yolo_model()
    analyzer = SmokeMotionAnalyzer(
        min_motion_mag=0.4,
        static_motion_ratio=0.04,
        upward_ratio_threshold=0.50,
        required_consecutive_frames=3
    )

    # 2. 카메라 또는 비디오 소스 열기
    src = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    
    if not cap.isOpened():
        print(f"❌ [에러] 영상 소스({args.source})를 열 수 없습니다.")
        return

    print("\n👉 조작 키 안내:")
    print("   [q] : 프로그램 종료")
    print("   [r] : 모션 분석 상태 리셋")
    print("   [s] : 현재 화면 캡처 저장\n")

    prev_time = time.time()
    fps = 0.0

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

        # 3. YOLO 추론 (verbose=False로 콘솔 로그 방지)
        results = model.predict(source=frame, conf=args.conf, save=False, verbose=False)
        boxes = results[0].boxes if len(results) > 0 else []

        smoke_boxes = []
        fire_boxes = []

        if len(boxes) > 0:
            names = results[0].names
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = str(names[cls_id]).lower()
                conf_val = float(box.conf[0])
                coords = [int(v) for v in box.xyxy[0]]

                if "smoke" in cls_name:
                    smoke_boxes.append((coords, conf_val))
                elif "fire" in cls_name:
                    fire_boxes.append((coords, conf_val))

        # 4. 모션 분석 및 시각화 (연기 박스가 있는 경우)
        has_real_smoke = False
        has_static_photo = False

        if smoke_boxes:
            # 가장 큰 연기 박스를 우선 분석
            smoke_boxes.sort(key=lambda b: (b[0][2] - b[0][0]) * (b[0][3] - b[0][1]), reverse=True)
            main_coords, conf_val = smoke_boxes[0]

            # 모션 분석 수행
            motion_res = analyzer.analyze(frame, main_coords, class_name="smoke")
            
            # 시각화 오버레이 (화살표 및 바운딩 박스)
            display_frame = analyzer.draw_motion_overlay(display_frame, motion_res)

            if motion_res.is_real_smoke:
                has_real_smoke = True
            elif motion_res.is_static_photo:
                has_static_photo = True

        elif fire_boxes:
            # 연기 없이 불꽃만 감지된 경우 (일반 화재 박스 표시)
            for coords, conf_val in fire_boxes:
                x1, y1, x2, y2 = coords
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 140, 255), 2)
                cv2.putText(display_frame, f"FIRE {conf_val*100:.1f}%", (x1, max(20, y1 - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 140, 255), 2)
        else:
            # 감지 객체가 없으면 모션 버퍼 리셋
            analyzer.reset()

        # 5. 상단 HUD 정보창 렌더링
        hud_bg = display_frame[:70, :].copy()
        cv2.rectangle(display_frame, (0, 0), (w, 70), (20, 20, 20), -1)
        cv2.addWeighted(display_frame[:70, :], 0.75, hud_bg, 0.25, 0, display_frame[:70, :])

        # 시스템 타이틀 & FPS
        cv2.putText(display_frame, "EDGE SAVER - PRE-FIRE EARLY DETECTION TEST", (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.putText(display_frame, f"FPS: {fps:.1f}", (w - 110, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # 조기 감지 판정 상태 표시
        if has_real_smoke:
            status_banner = ">> 🚨 [CONFIRMED] RISING SMOKE PLUME (EARLY DETECTION ACTIVE) <<"
            banner_color = (0, 0, 255) # 빨간색
        elif has_static_photo:
            status_banner = ">> 🛡️ [FILTER ACTIVE] STATIC PHOTO DETECTED (ALARM BLOCKED) <<"
            banner_color = (255, 140, 0) # 주황색
        elif smoke_boxes:
            status_banner = ">> ⏳ [ANALYZING] EVALUATING SMOKE UPWARD MOTION VECTORS..."
            banner_color = (0, 255, 255) # 노란색
        else:
            status_banner = ">> [STANDBY] AREA SAFE (SCANNING FOR PRE-FIRE ANOMALIES)..."
            banner_color = (180, 180, 180) # 회색

        cv2.putText(display_frame, status_banner, (15, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, banner_color, 2)

        # 6. 화면 출력
        cv2.imshow("Edge Saver Early Detection Tester", display_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("\n🛑 테스트 프로그램을 종료합니다.")
            break
        elif key == ord('r'):
            analyzer.reset()
            print("🔄 모션 분석기 상태가 리셋되었습니다.")
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
