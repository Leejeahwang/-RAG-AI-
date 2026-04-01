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
from fire_detector import detect_fire

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
    """
    global latest_frame, camera_running
    
    # 0번 카메라 열기 (CSI 또는 웹캠)
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ [에러] 카메라 디바이스를 열 수 없습니다.")
        camera_running = False
        return
        
    print("📷 [백그라운드] 카메라 수집 스레드가 켜졌습니다. (화면이 뜨지 않습니다)")
    
    while camera_running:
        ret, frame = cap.read()
        if ret:
            # 해상도를 640 너비로 리사이즈 (저장 및 AI 처리 속도 향상)
            h, w = frame.shape[:2]
            target_w = 640
            target_h = int(h * (target_w / w))
            resized_frame = cv2.resize(frame, (target_w, target_h))
            
            latest_frame = resized_frame
            
            # PC 테스트용 디버그 화면 (빠른 화면 갱신을 위해 스레드 내부에서 처리)
            if DEBUG_MODE:
                cv2.imshow("CCTV_DEBUG_PREVIEW", resized_frame)
                # 'q' 키를 누르면 프로세스 완전 종료
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("\n🛑 q 키 입력 감지! 무인 감시 모드를 강제 종료합니다.")
                    os._exit(0)
        else:
            time.sleep(0.1) # 프레임 깨짐/CPU 독점 방지
            
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
