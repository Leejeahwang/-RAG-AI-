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
import platform
import subprocess
import numpy as np
import config

try:
    from vision.fire_detector import detect_fire
except ModuleNotFoundError:
    from fire_detector import detect_fire

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURE_DIR = os.path.join(BASE_DIR, "captures")

# 전역 변수: 항상 최신 프레임을 1개만 기억
latest_frame = None
camera_running = True
camera_offline = False

# PC에서 테스트할 때 카메라 화면을 띄워보고 싶다면 True 로 변경하세요!
# 라즈베리파이(서버) 환경으로 넘어갈 때는 무조건 False 여야 합니다.
DEBUG_MODE = False

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

def try_read_frame(cap):
    """카메라가 실제로 프레임을 읽을 수 있는지 확인하고 첫 프레임을 반환합니다."""
    if cap is None or not cap.isOpened():
        return False, None
    try:
        ret, frame = cap.read()
        if ret and frame is not None:
            return True, frame
    except Exception as e:
        pass
    return False, None

def camera_worker_thread():
    """
    아무리 AI 추론이 느려져도 카메라 영상이 '지연(Lag)' 되지 않도록,
    계속해서 센서의 최신 화면만 덮어쓰기하는 백그라운드 스레드입니다.
    - macOS: AVFOUNDATION 백엔드로 즉시 연동 (인덱스 1)
    - Linux: GStreamer -> V4L2 -> 기본 폴백 시도 후, 최종 실패 시 rpicam-jpeg 명령어로 구동
    """
    global latest_frame, camera_running, camera_offline
    
    cap = None
    success = False
    use_rpicam = False
    current_os = platform.system()
    
    if current_os == 'Darwin':
        # 🍏 macOS 환경: AVFOUNDATION 다이렉트 연동
        try:
            cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_AVFOUNDATION)
            success, _ = try_read_frame(cap)
            if not success and cap:
                cap.release()
                cap = None
        except Exception as e:
            print(f"⚠️ macOS 카메라 초기화 실패: {e}")
            if cap: cap.release()
            cap = None
            
    elif current_os == 'Windows':
        # 🪟 Windows 환경: DirectShow(CAP_DSHOW) 기반 RGB 웹캠 자동 탐색
        candidate_indices = [getattr(config, 'CAMERA_INDEX', 1), 1, 0]
        seen = set()
        unique_candidates = [x for x in candidate_indices if not (x in seen or seen.add(x))]

        for c_idx in unique_candidates:
            try:
                temp_cap = cv2.VideoCapture(c_idx, cv2.CAP_DSHOW)
                s_read, test_frame = try_read_frame(temp_cap)
                if s_read and test_frame is not None:
                    # Windows Hello IR(적외선) 카메라의 검은 화면(std < 5) 방지
                    import numpy as np
                    if np.std(test_frame) > 5.0 or c_idx == unique_candidates[-1]:
                        cap = temp_cap
                        success = True
                        break
                if temp_cap:
                    temp_cap.release()
            except Exception:
                pass

        if not success:
            try:
                cap = cv2.VideoCapture(config.CAMERA_INDEX)
                success, _ = try_read_frame(cap)
                if not success and cap:
                    cap.release()
                    cap = None
            except Exception:
                if cap: cap.release()
                cap = None
                
    else:
        # 🐧 리눅스(라즈베리파이) 환경: 순차 폴백 시도
        # 1. GStreamer 우선 시도
        gst_pipeline = "libcamerasrc ! video/x-raw, width=640, height=480, format=RGB ! videoconvert ! appsink drop=true"
        try:
            cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
            success, _ = try_read_frame(cap)
            if not success and cap:
                cap.release()
                cap = None
        except Exception:
            if cap: cap.release()
            cap = None
            
        # 2. V4L2 드라이버로 폴백 시도
        if not success:
            try:
                cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_V4L2)
                success, _ = try_read_frame(cap)
                if not success and cap:
                    cap.release()
                    cap = None
            except Exception:
                if cap: cap.release()
                cap = None
                
        # 3. 기본 VideoCapture 폴백 시도
        if not success:
            try:
                cap = cv2.VideoCapture(config.CAMERA_INDEX)
                success, _ = try_read_frame(cap)
                if not success and cap:
                    cap.release()
                    cap = None
            except Exception:
                if cap: cap.release()
                cap = None
            
    # 4. 라즈베리파이 5 전용 rpicam-jpeg 도구 폴백 판단
    if not success or cap is None:
        if is_linux:
            print("⚠️ [경고] OpenCV로 카메라 장치를 열 수 없습니다. 라즈베리파이 5 전용 'rpicam-jpeg' 백엔드로 전환합니다.")
            use_rpicam = True
            camera_offline = False
        else:
            print("❌ [에러] 카메라 디바이스를 열 수 없습니다. 감시 기능 없이 센서 모드로 작동합니다.")
            camera_offline = True
            camera_running = False
            return
    else:
        camera_offline = False
        
    print("📷 [백그라운드] 카메라 수집 스레드가 켜졌습니다. (화면이 뜨지 않습니다)")
    
    rpicam_fail_count = 0
    
    while camera_running:
        if not use_rpicam:
            success_read, frame = try_read_frame(cap)
            if success_read and frame is not None:
                # 해상도를 640 너비로 리사이즈
                h, w = frame.shape[:2]
                target_w = 640
                target_h = int(h * (target_w / w))
                resized_frame = cv2.resize(frame, (target_w, target_h))
                latest_frame = resized_frame
            else:
                time.sleep(0.01)
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
                        rpicam_fail_count = 0  # 성공 시 카운트 리셋
                else:
                    raise FileNotFoundError("rpicam-jpeg returned non-zero code or empty stdout")
            except Exception as e:
                rpicam_fail_count += 1
                if rpicam_fail_count <= 3:
                    print(f"❌ [에러] rpicam 캡처 실패: {e}")
                elif rpicam_fail_count == 4:
                    print("❌ [에러] rpicam 캡처 오류가 계속되어 로그 출력을 제한하고 대기 주기를 늘립니다.")
                
                sleep_time = 5.0 if rpicam_fail_count > 3 else 0.5
                time.sleep(sleep_time)
                continue
                
            time.sleep(0.02)  # 불필요한 0.5초 대기 제거하여 프레임 갱신율 극대화

            
    if not use_rpicam and cap is not None and cap.isOpened():
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