"""
Edge Saver 비전 모듈 백그라운드 서비스 (cctv_service.py) - Mac 최종 수정본
"""

import cv2
import os
import time
import datetime
import threading

try:
    from vision.fire_detector import detect_fire
except ModuleNotFoundError:
    from fire_detector import detect_fire

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURE_DIR = os.path.join(BASE_DIR, "captures")

latest_frame = None
camera_running = True
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
    global latest_frame, camera_running
    
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ [에러] 카메라 디바이스를 열 수 없습니다.")
        camera_running = False
        return
        
    print("📷 [백그라운드] 카메라 수집 스레드가 켜졌습니다.")
    
    while camera_running:
        ret, frame = cap.read()
        if ret:
            h, w = frame.shape[:2]
            target_w = 640
            target_h = int(h * (target_w / w))
            resized_frame = cv2.resize(frame, (target_w, target_h))
            
            latest_frame = resized_frame
        else:
            time.sleep(0.1)
            
    cap.release()

def start_cctv_service(scan_interval_sec=5):
    global latest_frame, camera_running

    if not os.path.exists(CAPTURE_DIR):
        os.makedirs(CAPTURE_DIR)
        
    print(f"\n🚀 [엣지 세이버 CCTV 시작] {scan_interval_sec}초 간격으로 무인 화재 감시를 시작합니다.")
    print("👉 (중지하려면 화면 클릭 후 'q' 키를 누르거나 터미널에서 Ctrl+C를 누르세요)\n")

    cam_thread = threading.Thread(target=camera_worker_thread, daemon=True)
    cam_thread.start()
    
    time.sleep(2) 
    
    last_scan_time = time.time()
    cleanup_counter = 0
    
    try:
        while camera_running:
            current_frame = latest_frame
            
            if current_frame is not None:
                # Mac의 화면 멈춤 방지를 위해 GUI는 무조건 메인 루프에서 처리
                if DEBUG_MODE:
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
                    
                    # 프레임 저장
                    cv2.imwrite(save_path, current_frame)
                    
                    # Mac 폴더 권한 문제로 저장이 안 되었을 경우 예외 처리
                    if not os.path.exists(save_path):
                        print("❌ [에러] Mac 권한 문제: 캡처 이미지를 폴더에 저장하지 못했습니다.")
                        continue
                    
                    # 🚀 윈도우 원본과 똑같이 실제 AI 화재 판별 엔진 호출
                    analysis = detect_fire(save_path)
                    
                    # 💡 분석 결과 (정확도 등) 상세 출력
                    print(f"🔎 [AI 분석 결과] {analysis}")
                    
                    if "오류" in analysis.get('description', '') or "초기화" in analysis.get('description', ''):
                        print(f"[{timestamp}] 🚨 시스템 에러: {analysis.get('description')}")
                    elif analysis.get("fire_detected"):
                        print(f"[{timestamp}] {analysis.get('description')} -> 🔥 화재 경보 로직 호출!")
                    else:
                        print(f"[{timestamp}] 특이사항 없음 (안전)")
                        
                    # 평시/오류 시 즉시 삭제 (디스크 낭비 방지)
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