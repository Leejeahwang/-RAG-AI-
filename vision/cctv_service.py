"""
Edge Saver 비전 모듈 백그라운드 서비스 (cctv_service.py) - Mac & RPi5 통합 최종 수정본
"""

import cv2
import os
import time
import datetime
import threading
import platform
import numpy as np
import config

try:
    from vision.fire_detector import detect_fire
except ModuleNotFoundError:
    from fire_detector import detect_fire

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURE_DIR = os.path.join(BASE_DIR, "captures")

latest_frame = None
camera_running = True
camera_offline = False
DEBUG_MODE = True

def cleanup_old_captures(days=3):
    now = time.time()
    cutoff = now - (days * 86400)
    
    if not os.path.exists(CAPTURE_DIR):
        return
        
    deleted_count = 0
    for filename in os.listdir(CAPTURE_DIR):
        if filename.endswith(".jpg"):
            filepath = os.path.join(CAPTURE_DIR, filename)
            file_mtime = os.path.getmtime(filepath)
            
            if file_mtime < cutoff:
                try:
                    os.remove(filepath)
                    deleted_count += 1
                except Exception as e:
                    pass
    
    if deleted_count > 0:
        print(f"🧹 [청소 완료] {days}일 이상 지난 과거 캡처 파일 {deleted_count}개를 자동 삭제했습니다.")

def camera_worker_thread():
    global latest_frame, camera_running, camera_offline
    
    is_linux = (platform.system() == 'Linux')
    cap = None
    picam = None
    
    # 1. OS 환경에 따른 카메라 장치 초기화
    if is_linux:
        print("🔄 [시스템] 라즈베리파이 5 최적화: 고성능 Picamera2 엔진을 구동합니다.")
        try:
            from picamera2 import Picamera2
            picam = Picamera2()
            # 640x480 사이즈로 가볍게 프레임 설정
            config_pc = picam.create_preview_configuration(main={"format": "RGB888", "size": (640, 480)})
            picam.configure(config_pc)
            picam.start()
            camera_offline = False
        except Exception as e:
            print(f"❌ [에러] 라즈베리파이 전용 Picamera2 초기화 실패: {e}")
            camera_offline = True
    else:
        print("🍏 [시스템] macOS 환경 검출: 표준 OpenCV VideoCapture를 구동합니다.")
        cap = cv2.VideoCapture(config.CAMERA_INDEX)
        if cap.isOpened():
            camera_offline = False
        else:
            print("⚠️ [경고] 기본 카메라를 열 수 없습니다.")
            camera_offline = True

    print("📷 [백그라운드] 카메라 수집 스레드가 정상 가동되었습니다.")
    
    # 2. 실시간 프레임 수집 루프
    while camera_running:
        if not camera_offline:
            if is_linux: # 💡 라즈베리파이 5 구동 로직
                try:
                    frame = picam.capture_array()
                    # Picamera2의 오리지널 RGB 이미지를 OpenCV 표준인 BGR로 즉시 변환
                    latest_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    time.sleep(0.03) # 약 30 FPS 안정화 유지
                except Exception as e:
                    print(f"❌ [에러] 실시간 프레임 수집 실패: {e}")
                    time.sleep(0.5)
            else: # 💡 Mac 구동 로직
                ret, frame = cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    target_w = 640
                    target_h = int(h * (target_w / w))
                    latest_frame = cv2.resize(frame, (target_w, target_h))
                    time.sleep(0.01)
                else:
                    time.sleep(0.1)
        else:
            # 카메라 하드웨어가 비정상일 때 시스템 정지를 막기 위한 더미 이미지 피드 생성
            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(dummy_frame, "CAMERA OFFLINE (NO HARDWARE)", (50, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            latest_frame = dummy_frame
            time.sleep(1.0)
            
    # 3. 자원 해제 복구 작업
    if is_linux and picam is not None:
        picam.stop()
        print("🔒 [해제] 라즈베리파이 카메라 장치를 정상 종료했습니다.")
    elif cap is not None and cap.isOpened():
        cap.release()
        print("🔒 [해제] Mac 카메라 장치를 정상 해제했습니다.")

def start_cctv_service(scan_interval_sec=5):
    global latest_frame, camera_running

    if not os.path.exists(CAPTURE_DIR):
        os.makedirs(CAPTURE_DIR)
        
    print(f"\n🚀 [엣지 세이버 CCTV 시작] {scan_interval_sec}초 간격으로 무인 화재 감시를 시작합니다.")
    print("👉 (중지하려면 화면 클릭 후 'q' 키를 누르세요)\n")

    cam_thread = threading.Thread(target=camera_worker_thread, daemon=True)
    cam_thread.start()
    
    time.sleep(2) 
    
    last_scan_time = time.time()
    cleanup_counter = 0
    
    try:
        while camera_running:
            current_frame = latest_frame
            
            if current_frame is not None:
                if DEBUG_MODE:
                    # 가속이 없는 환경(llvmpipe)에서도 OpenCV가 CPU로 화면 창을 무조건 강제 팝업합니다.
                    cv2.imshow("CCTV_DEBUG_PREVIEW", current_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("\n🛑 q 키 입력 감지! 무인 감시 모드를 강제 종료합니다.")
                        break

                now = time.time()
                if now - last_scan_time >= scan_interval_sec:
                    last_scan_time = now 
                    cleanup_counter += 1
                    
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    save_path = os.path.join(CAPTURE_DIR, f"scan_{timestamp}.jpg")
                    
                    cv2.imwrite(save_path, current_frame)
                    
                    if not os.path.exists(save_path):
                        print("❌ [에러] 파일 권한 문제: 캡처 이미지를 폴더에 저장하지 못했습니다.")
                        continue
                    
                    analysis = detect_fire(save_path)
                    print(f"🔎 [AI 분석 결과] {analysis}")
                    
                    if "오류" in analysis.get('description', '') or "초기화" in analysis.get('description', ''):
                        print(f"[{timestamp}] 🚨 시스템 에러: {analysis.get('description')}")
                    elif analysis.get("fire_detected"):
                        print(f"[{timestamp}] {analysis.get('description')} -> 🔥 화재 경보 로직 호출!")
                    else:
                        print(f"[{timestamp}] 특이사항 없음 (안전)")
                        
                    if not analysis.get("fire_detected") and os.path.exists(save_path):
                        os.remove(save_path)
                            
                    if cleanup_counter > 100:
                        cleanup_old_captures(days=3)
                        cleanup_counter = 0
            else:
                time.sleep(0.1)
                
    except KeyboardInterrupt:
        print("\n🛑 사용자에 의해 CCTV 무인 감시 모드가 종료되었습니다.")
    finally:
        camera_running = False
        cam_thread.join(timeout=2) 
        if DEBUG_MODE:
            cv2.destroyAllWindows()
            cv2.waitKey(1) 
        print("기기 카메라 렌즈 작동 종료.")

if __name__ == "__main__":
    start_cctv_service(scan_interval_sec=5)