import os
import sys
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DATA_YAML = os.path.join(BASE_DIR, "dataset", "data.yaml")

# 1. 모델 경로 정의
YOLO10M_PT = os.path.join(MODELS_DIR, "YOLOv10-FireSmoke-M.pt")
NEW_V8N_PT = os.path.join(MODELS_DIR, "new_yolov8n_yolov8n.pt")

def export_model(model_path, format_name, half=False, int8=False, data_path=None):
    if not os.path.exists(model_path):
        print(f"❌ 모델 파일을 찾을 수 없습니다: {model_path}")
        return False
        
    print(f"\n🔄 Model: {os.path.basename(model_path)} -> Exporting to {format_name} (half={half}, int8={int8})...")
    try:
        model = YOLO(model_path)
        if int8:
            out_path = model.export(format=format_name, int8=True, data=data_path, imgsz=640)
        else:
            out_path = model.export(format=format_name, half=half, imgsz=640)
        print(f"✅ Export 완료! 경로: {out_path}")
        return True
    except Exception as e:
        print(f"❌ Export 실패: {e}")
        return False

def main():
    print("⚡ [일괄 변환 시작] 9-Way 벤치마크 비교군 모델 생성 중...")
    
    # 1. YOLOv10m FP16 변환 (OpenVINO FP16)
    yolo10m_fp16_path = os.path.join(MODELS_DIR, "YOLOv10-FireSmoke-M_openvino_model")
    if os.path.exists(yolo10m_fp16_path):
        print(f"⏭️ YOLOv10m FP16 모델이 이미 존재하여 건너뜁니다: {yolo10m_fp16_path}")
    else:
        export_model(YOLO10M_PT, "openvino", half=True)
    
    # 2. 신규 YOLOv8n FP16 변환 (OpenVINO FP16)
    new_v8n_fp16_path = os.path.join(MODELS_DIR, "new_yolov8n_yolov8n_openvino_model")
    if os.path.exists(new_v8n_fp16_path):
        print(f"⏭️ New YOLOv8n FP16 모델이 이미 존재하여 건너뜁니다: {new_v8n_fp16_path}")
    else:
        export_model(NEW_V8N_PT, "openvino", half=True)
    
    # 3. 신규 YOLOv8n INT8 변환 (OpenVINO INT8)
    new_v8n_int8_path = os.path.join(MODELS_DIR, "new_yolov8n_yolov8n_int8_openvino_model")
    # ultralytics가 openvino int8 폴더명을 _int8_openvino_model 또는 _openvino_model로 생성할 수 있으므로 둘 다 확인
    alt_new_v8n_int8_path = os.path.join(MODELS_DIR, "new_yolov8n_yolov8n_openvino_model")
    # 만약 기존에 FP16과 동일한 이름으로 덮어쓸까봐 OpenVINO INT8 변환은 가급적 _int8_openvino_model 로 체크
    if os.path.exists(new_v8n_int8_path):
        print(f"⏭️ New YOLOv8n INT8 모델이 이미 존재하여 건너뜁니다: {new_v8n_int8_path}")
    else:
        if os.path.exists(DATA_YAML):
            export_model(NEW_V8N_PT, "openvino", int8=True, data_path=DATA_YAML)
        else:
            print(f"⚠️ 캘리브레이션 데이터셋이 없어 INT8 변환을 기본값으로 진행합니다: {DATA_YAML}")
            export_model(NEW_V8N_PT, "openvino", int8=True)
        
    print("\n🎉 모든 변환 프로세스가 끝났습니다. models 폴더를 확인해 주세요.")

if __name__ == "__main__":
    main()
