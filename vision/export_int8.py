import os
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "fire_smoke.pt")
DATA_YAML = os.path.join(BASE_DIR, "dataset", "data.yaml")

def export_to_int8():
    if not os.path.exists(MODEL_PATH):
        print(f"❌ 기본 모델 파일이 없습니다: {MODEL_PATH}")
        return

    print(f"🔄 기본 모델({MODEL_PATH}) 로드 중...")
    model = YOLO(MODEL_PATH)

    print(f"⚡ INT8 양자화 Export 시작 (데이터셋: {DATA_YAML})...")
    print("이 작업은 수십 초 ~ 몇 분 정도 소요될 수 있습니다.")
    
    try:
        # OpenVINO 형식으로 int8 양자화 내보내기 수행 (라즈베리파이 CPU 최적화)
        # half=False (FP16 안함), int8=True
        output_path = model.export(format="openvino", int8=True, data=DATA_YAML, imgsz=640)
        print(f"✅ INT8 양자화 완료! 출력 경로: {output_path}")
    except Exception as e:
        print(f"❌ 양자화 실패: {e}")

if __name__ == "__main__":
    export_to_int8()
