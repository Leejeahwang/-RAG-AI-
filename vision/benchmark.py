import os
import time
import glob
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DATASET_DIR = os.path.join(BASE_DIR, "dataset")

# 1. 테스트 이미지셋 확보 (dataset 내의 모든 JPG 이미지)
test_images = glob.glob(os.path.join(DATASET_DIR, "*.jpg"))
if not test_images:
    print(f"❌ 벤치마크를 위한 테스트 이미지가 {DATASET_DIR}에 없습니다.")
    exit(1)

print(f"✅ 총 {len(test_images)}장의 화재/연기 이미지로 벤치마크를 수행합니다.")

# 2. 모델 경로 정의
MODELS = {
    # 1. 기존 YOLOv8 (화재 학습)
    "YOLOv8 (FP32)": os.path.join(MODELS_DIR, "fire_smoke.pt"),
    "YOLOv8 (FP16)": os.path.join(MODELS_DIR, "fire_smoke.onnx"),
    "YOLOv8 (INT8)": os.path.join(MODELS_DIR, "fire_smoke_int8_openvino_model"),
    
    # 2. 기존 YOLOv10m (화재 학습)
    "YOLOv10m (FP32)": os.path.join(MODELS_DIR, "YOLOv10-FireSmoke-M.pt"),
    "YOLOv10m (FP16)": os.path.join(MODELS_DIR, "YOLOv10-FireSmoke-M_openvino_model"),
    "YOLOv10m (INT8)": os.path.join(MODELS_DIR, "YOLOv10-FireSmoke-M_int8_openvino_model"),
    
    # 3. 신규 YOLOv8n (Al Numan 모델)
    "New YOLOv8n (FP32)": os.path.join(MODELS_DIR, "new_yolov8n_yolov8n.pt"),
    "New YOLOv8n (FP16)": os.path.join(MODELS_DIR, "new_yolov8n_yolov8n_openvino_model"),
    "New YOLOv8n (INT8)": os.path.join(MODELS_DIR, "new_yolov8n_yolov8n_int8_openvino_model"),
}

# 이름이 다르게 생성될 수 있는 양자화 폴더 경로 보정
for name, path in list(MODELS.items()):
    if "openvino" in path and not os.path.exists(path):
        alt_path = path.replace("_int8_openvino_model", "_openvino_model")
        if os.path.exists(alt_path):
            MODELS[name] = alt_path
        else:
            alt_path2 = path.replace("_openvino_model", "_int8_openvino_model")
            if os.path.exists(alt_path2):
                MODELS[name] = alt_path2

def get_dir_size_mb(path):
    """파일 또는 디렉토리의 크기를 MB 단위로 반환합니다."""
    if os.path.isdir(path):
        total_size = 0
        for root, dirs, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if os.path.exists(fp):
                    total_size += os.path.getsize(fp)
        return total_size / (1024 * 1024)
    else:
        return os.path.getsize(path) / (1024 * 1024)

def get_cpu_temp():
    """라즈베리파이 CPU 온도를 가져옵니다 (지원하지 않는 플랫폼은 None 반환)."""
    try:
        # 라즈베리파이(리눅스)의 CPU 온도 확인 시스템 파일
        if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_raw = f.read()
            return float(temp_raw) / 1000.0
    except:
        pass
    return None

print(f"\n🚀 [엣지 세이버 9-Way 77장 데이터셋 벤치마크] 테스트 시작")
print("-" * 95)

results = []
FIRE_CLASSES = {'fire', 'smoke', 'fire', 'smoke', 'FIRE', 'SMOKE'}

for name, path in MODELS.items():
    if not os.path.exists(path):
        print(f"⚠️ {name} 모델을 찾을 수 없습니다: {path}")
        continue
        
    print(f"🔄 [{name}] 모델 로드 및 워밍업 중...", end="", flush=True)
    
    try:
        size_mb = get_dir_size_mb(path)
        model = YOLO(path, task="detect")
        
        # 워밍업
        model.predict(source=test_images[0], conf=0.1, verbose=False)
        print(" 워밍업 완료. 추론 루프 가동...", flush=True)
        
        latencies = []
        confidence_sum = 0.0
        detected_frames = 0
        
        # 온도 모니터링 변수 초기화
        start_temp = get_cpu_temp()
        max_temp = start_temp
        
        for img_path in test_images:
            start_t = time.time()
            res = model.predict(source=img_path, conf=0.1, verbose=False)
            latencies.append(time.time() - start_t)
            
            # 실시간 온도 추적
            curr_temp = get_cpu_temp()
            if curr_temp is not None:
                if max_temp is None or curr_temp > max_temp:
                    max_temp = curr_temp
            
            # 화재/연기 관련 객체가 감지되었는지 필터링하여 최대 신뢰도 추출
            if len(res) > 0 and len(res[0].boxes) > 0:
                names = res[0].names
                max_fire_conf = 0.0
                has_fire = False
                
                for box in res[0].boxes:
                    cls_name = names[int(box.cls[0])]
                    conf = float(box.conf[0])
                    
                    # 화재나 연기 클래스에 포함되는지 검사
                    if cls_name.lower() in FIRE_CLASSES:
                        has_fire = True
                        if conf > max_fire_conf:
                            max_fire_conf = conf
                
                if has_fire:
                    confidence_sum += max_fire_conf
                    detected_frames += 1
                    
        avg_latency = (sum(latencies) / len(test_images)) * 1000  # ms
        # 화재 감지율
        detection_rate = (detected_frames / len(test_images)) * 100
        # 감지된 프레임에서의 평균 신뢰도
        avg_conf = (confidence_sum / detected_frames) * 100 if detected_frames > 0 else 0.0
        
        # 온도 결과 포맷팅
        if start_temp is not None and max_temp is not None:
            temp_str = f"{start_temp:.1f}℃ -> {max_temp:.1f}℃"
        else:
            temp_str = "N/A"
            
        results.append({
            "Model": name,
            "Size": f"{size_mb:.1f}",
            "Latency": f"{avg_latency:.1f}",
            "Conf": f"{avg_conf:.1f}%" if detected_frames > 0 else "0.0%",
            "Rate": f"{detection_rate:.1f}%",
            "Temp": temp_str
        })
        
        temp_log = f" | 발열: {temp_str}" if start_temp is not None else ""
        print(f"   └─ 속도: {avg_latency:.1f}ms | 감지율: {detection_rate:.1f}% | 평균 신뢰도: {avg_conf:.1f}%{temp_log}")
        
    except Exception as e:
        print(f"\n❌ {name} 테스트 중 오류 발생: {e}")

print("\n" + "=" * 95)
print("📊 9-Way 데이터셋 전체(77장) 벤치마크 최종 결과 (발열 모니터링 포함)")
print("=" * 95)
print(f"{'모델 형식':<24} | {'용량(MB)':<8} | {'속도(ms)':<10} | {'화재 감지율':<12} | {'평균 신뢰도':<12} | {'발열 변화(시작->최대)'}")
print("-" * 95)
for r in results:
    print(f"{r['Model']:<24} | {r['Size']:<8} | {r['Latency']:<10} | {r['Rate']:<12} | {r['Conf']:<12} | {r['Temp']}")
print("=" * 95)
print("\n✅ 전체 데이터셋 기반 벤치마킹이 완료되었습니다. 이 결과를 바탕으로 benchmark_results_9way.md를 갱신합니다.")
