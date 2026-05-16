import cv2
import os
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
print(f"🔥 [라이브 테스트] 화재 감지기 구동 준비 중...")
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

while True:
    ret, frame = cap.read()
    if not ret:
        print("❌ 프레임을 읽어올 수 없습니다.")
        break
    
    # 모델을 통해 화면의 불꽃/연기 탐지 (신뢰도 10% 이상)
    # YOLOv10은 속도가 빠르므로 매 프레임 직접 분석 가능
    results = model.predict(source=frame, conf=0.1, verbose=False)
    
    # 객체 위치(바운딩 박스)가 그려진 이미지 추출
    annotated_frame = results[0].plot()
    
    # 윈도우 창에 띄우기
    cv2.imshow("Live Fire Detection Test (YOLOv10-M)", annotated_frame)
    
    # 'q' 키 입력 시 루프 탈출
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("🛑 사용자가 테스트를 종료했습니다.")
        break

# 자원 해제
cap.release()
cv2.destroyAllWindows()
