"""
Edge Saver 비전 모듈 백그라운드 서비스 (cctv_service.py)

화면(UI) 없이 백그라운드에서 동작하는 오프라인 24시간 감시 루프입니다.
- 카메라 프레임 상시 리드 (Thread 방식 분리)
- 3~5초 단위 주기적 AI 판별 (타임랩스)
- 하드디스크 관리를 위한 오래된 캡처본(3일 전) 자동 삭제 기능
"""

import cv2
import os
import time
import datetime
import threading
try:
    from vision.fire_detector import detect_fire
except ImportError:
    from fire_detector import detect_fire

import subprocess
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURE_DIR = os.path.join(BASE_DIR, "captures")

# 전역 변수: 항상 최신 프레임을 1개만 기억
latest_frame = None
camera_running = True

# PC에서 테스트할 때 카메라 화면을 띄워보고 싶다면 True 로 변경하세요!
# 라즈베리파이(서버) 환경으로 넘어갈 때는 무조건 False 여야 합니다.
DEBUG_MODE = True

def cleanup_old_captures(days=3):
    """
    저장소 용량 관리를 위해 지정된 일수(days) 이전의 캡처 이미지를 삭제합니다.
    """
    now = time.time()
    cutoff = now - (days * 86400) # 86400초 = 1일
    
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
    """
    아무리 AI 추론이 느려져도 카메라 영상이 '지연(Lag)' 되지 않도록,
    계속해서 센서의 최신 화면만 덮어쓰기하는 백그라운드 스레드입니다.
    라즈베리파이 5의 경우 rpicam-jpeg 폴백을 지원합니다.
    """
    global latest_frame, camera_running
    
    # 1. 먼저 일반 OpenCV 방식으로 시도
    cap = cv2.VideoCapture(0)
    use_rpicam = False
    
    if cap.isOpened():
        ret, frame = cap.read()
        if not ret or frame is None:
            print("⚠️ [경고] 기본 카메라 장치에서 빈 화면이 들어옵니다. (라즈베리파이 5 대응)")
            use_rpicam = True
            cap.release()
    else:
        print("⚠️ [경고] 기본 카메라를 열 수 없습니다.")
        use_rpicam = True

    if use_rpicam:
        print("🔄 [시스템] 라즈베리파이 전용 rpicam-jpeg 캡처 모드로 전환합니다.")
        
    print("📷 [백그라운드] 카메라 수집 스레드가 활성화되었습니다.")
    
    while camera_running:
        if not use_rpicam:
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                target_w = 640
                target_h = int(h * (target_w / w))
                resized_frame = cv2.resize(frame, (target_w, target_h))
                latest_frame = resized_frame
                
                if DEBUG_MODE:
                    cv2.imshow("CCTV_DEBUG_PREVIEW", resized_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("\n🛑 q 키 입력 감지! 무인 감시 모드를 강제 종료합니다.")
                        os._exit(0)
            else:
                time.sleep(0.1)
        else:
            try:
                # rpicam-jpeg 명령어를 사용해 메모리로 직접 사진 캡처 (라즈베리파이 5 최적화)
                cmd = ["rpicam-jpeg", "-t", "1", "-n", "-o", "-", "--width", "640", "--height", "480"]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                
                if result.returncode == 0 and result.stdout:
                    image_array = np.frombuffer(result.stdout, dtype=np.uint8)
                    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
                    if frame is not None:
                        latest_frame = frame
                        if DEBUG_MODE:
                            cv2.imshow("CCTV_DEBUG_PREVIEW", frame)
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                os._exit(0)
            except Exception as e:
                print(f"❌ [에러] rpicam 캡처 실패: {e}")
            time.sleep(0.5)
            
    if not use_rpicam and cap is not None:
        cap.release()

def start_cctv_service(scan_interval_sec=5):
    """
    주기적으로 최신 프레임을 꺼내와 화재를 감지하는 메인 감시 루프입니다. (타임랩스 방식)
    """
    global latest_frame, camera_running

    if not os.path.exists(CAPTURE_DIR):
        os.makedirs(CAPTURE_DIR)
        
    print(f"\n🚀 [엣지 세이버 CCTV 시작] {scan_interval_sec}초 간격으로 무인 화재 감시를 시작합니다.")
    print("👉 (중지하려면 터미널에서 Ctrl+C 를 누르세요)\n")

    # 카메라 백그라운드 수집 스레드 실행
    cam_thread = threading.Thread(target=camera_worker_thread, daemon=True)
    cam_thread.start()
    
    # 카메라가 켜질 때까지 잠시 대기
    time.sleep(2)
    
    try:
        cleanup_counter = 0
        
        while True:
            # 1. 버퍼에 담긴 최신 프레임 획득
            current_frame = latest_frame
            
            if current_frame is not None:
                # 2. 이번 프레임을 디스크에 임시 저장 (모델 분석용)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(CAPTURE_DIR, f"scan_{timestamp}.jpg")
                
                # 라즈베리파이 센서 좌우 반전을 고려한다면 cv2.flip 추가, 여기서는 생략
                cv2.imwrite(save_path, current_frame)
                
                # 3. 로컬 오프라인 YOLO 엔진에 화재 판별 요청
                analysis = detect_fire(save_path)
                
                # 모델 자체가 초기화 안 된 에러 상황 처리
                if "오류" in analysis['description'] or "초기화" in analysis['description']:
                    print(f"[{timestamp}] 🚨 시스템 에러: {analysis['description']}")
                    # 에러 시에도 디스크 낭비 방지를 위해 임시 파일은 지웁니다
                    if os.path.exists(save_path):
                        os.remove(save_path)
                elif analysis["fire_detected"]:
                    print(f"[{timestamp}] {analysis['description']} -> 🔥 화재 경보 로직(RAG/음성) 호출 필요!")
                    # TODO: 이 시점에 main.py 나 Alerts 시스템으로 이벤트를 던져야 합니다. (이벤트 브릿지)
                else:
                    print(f"[{timestamp}] 특이사항 없음 (안전) - 삭제 처리")
                    # 평시 사진은 디스크 공간 낭비이므로 확인 후 즉시 삭제!
                    if os.path.exists(save_path):
                        os.remove(save_path)
                
            else:
                print("⚠️ [경고] 카메라에서 프레임을 읽어오고 있지 않습니다.")
                
            # 4. 다음 스캔(5초) 대기 (대기하는 동안 백로그 큐에는 항상 1개의 현재 화면만 최신으로 유지됨)
            time.sleep(scan_interval_sec)
            
            # 5. 주기적으로 (약 100번 스캔 = 대략 8분에 한 번 꼴) 오래된 파일 삭제기 가동
            cleanup_counter += 1
            if cleanup_counter > 100:
                cleanup_old_captures(days=3)
                cleanup_counter = 0
                
    except KeyboardInterrupt:
        print("\n🛑 사용자에 의해 CCTV 무인 감시 모드가 종료되었습니다.")
    finally:
        camera_running = False
        cam_thread.join()
        if DEBUG_MODE:
            cv2.destroyAllWindows()
        print("기기 카메라 렌즈 작동 종료.")

if __name__ == "__main__":
    start_cctv_service(scan_interval_sec=5)
