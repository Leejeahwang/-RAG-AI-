import cv2
import os
import time
try:
    from ultralytics import YOLO
except ImportError:
    print("❌ ultralytics 라이브러리가 필요합니다.")
    exit(1)

# 로컬 모델 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")

# 1순위: 최신 INT8 모델, 2순위: 최신 원본 모델
MODEL_PATH = os.path.join(MODEL_DIR, "YOLOv10-FireSmoke-M_int8_openvino_model")
if not os.path.exists(MODEL_PATH):
    MODEL_PATH = os.path.join(MODEL_DIR, "YOLOv10-FireSmoke-M.pt")

print("=" * 50)
print(f"🌱 [에코 모드 라이브 테스트] 최대 자원 절약 모드 구동 중...")
print(f"👉 사용 모델: {os.path.basename(MODEL_PATH)}")
print("=" * 50)

# 모델 로드
model = YOLO(MODEL_PATH, task="detect")
print("✅ 모델 로드 완료! 노트북 웹캠을 켭니다...")
print("💡 화면을 끄려면 영문 'q' 키를 누르세요.")

# 웹캠 캡처 객체 생성 (0번 카메라)
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ 웹캠을 열 수 없습니다. 카메라 권한이나 연결 상태를 확인해주세요.")
    exit(1)

# 자원 절약 설정
SCAN_INTERVAL = 2.0  # 2초마다 한 번씩만 AI 검사 (0.5 FPS)
CONFIDENCE_THRESHOLD = 0.5  # 규태님 요청: 50% 이상일 때만 화재로 간주

last_scan_time = 0
last_annotated_frame = None

while True:
    ret, frame = cap.read()
    if not ret:
        print("❌ 프레임을 읽어올 수 없습니다.")
        break
    
    current_time = time.time()
    
    # 2초(SCAN_INTERVAL)가 지났을 때만 YOLO AI 모델 작동 (라즈베리파이 발열 방지 핵심)
    if current_time - last_scan_time >= SCAN_INTERVAL:
        # 모델을 통해 화면의 불꽃/연기 탐지 (신뢰도 50% 이상)
        results = model.predict(source=frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
        
        # 감지 결과 확인
        result = results[0]
        boxes = result.boxes
        
        if len(boxes) > 0:
            # 하나라도 50% 이상 감지되었다면 경보 울리기
            max_conf = 0.0
            detected_classes = set()
            names = result.names 
            
            for box in boxes:
                conf = float(box.conf[0])
                cls_name = names[int(box.cls[0])].upper()
                detected_classes.add(cls_name)
                if conf > max_conf:
                    max_conf = conf
                    
            classes_str = ", ".join(detected_classes)
            
            # 🔥 화재 감지 경보 출력 (터미널)
            print(f"🚨 [경보 발령] 화재 위험 요소 발견! 종류: [{classes_str}] (확신도: {max_conf*100:.1f}%)")
        else:
            # 50% 넘는 화재가 없을 경우 안전 표시 (옵션)
            # print("✅ [안전] 감지된 화재/연기 없음.")
            pass
            
        # 화면 출력을 위해 바운딩 박스가 그려진 이미지 갱신
        last_annotated_frame = result.plot()
        last_scan_time = current_time

    # AI가 갱신한 이미지가 있으면 띄워주고, 없으면 그냥 카메라 원본 띄워주기
    display_frame = last_annotated_frame if last_annotated_frame is not None else frame
    
    # 좌측 상단에 에코 모드 상태 표시
    cv2.putText(display_frame, "ECO MODE (Scan: 2s)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    
    # 윈도우 창에 띄우기
    cv2.imshow("Eco Fire Detection Test (YOLOv10-M)", display_frame)
    
    # 'q' 키 입력 시 루프 탈출
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("🛑 사용자가 테스트를 종료했습니다.")
        break

# 자원 해제
cap.release()
cv2.destroyAllWindows()
