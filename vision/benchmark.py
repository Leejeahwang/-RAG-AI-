import os
import time
import glob
try:
    from ultralytics import YOLO
except ImportError:
    print("❌ ultralytics 라이브러리가 필요합니다.")
    exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
CAPTURE_DIR = os.path.join(BASE_DIR, "captures")

# 벤치마킹에 사용할 임의의 캡처 이미지 (최신)
test_images = glob.glob(os.path.join(CAPTURE_DIR, "*.jpg"))
if not test_images:
    print(f"❌ 벤치마크를 위한 테스트 이미지가 {CAPTURE_DIR}에 없습니다.")
    exit(1)
TEST_IMAGE = test_images[0]

# 모델 경로 정의
MODELS = {
    "Base (FP32)": os.path.join(MODELS_DIR, "fire_smoke.pt"),
    "FP16 (ONNX)": os.path.join(MODELS_DIR, "fire_smoke.onnx"),
}

# INT8 openvino 경로 탐색 (ultralytics export 결과물 경로 매칭)
int8_candidates = [
    os.path.join(MODELS_DIR, "fire_smoke_openvino_model"),
    os.path.join(MODELS_DIR, "fire_smoke_int8_openvino_model"),
]
for cand in int8_candidates:
    if os.path.exists(cand):
        MODELS["INT8 (TFLite)"] = cand
        break

if "INT8 (TFLite)" not in MODELS:
    print("⚠️ INT8 모델 파일을 찾을 수 없습니다. (아직 생성되지 않았거나 경로가 다름)")

print(f"\n🚀 [엣지 세이버 벤치마크] 테스트 시작")
print(f"테스트 이미지: {os.path.basename(TEST_IMAGE)}")
print("-" * 50)

results = []

for name, path in MODELS.items():
    if not os.path.exists(path):
        print(f"⚠️ {name} 모델을 찾을 수 없습니다: {path}")
        continue
        
    print(f"\n🔄 [{name}] 모델 로드 및 워밍업 중...")
    
    try:
        # 1. 용량 측정
        size_mb = os.path.getsize(path) / (1024 * 1024)
        
        # 2. 모델 로드
        model = YOLO(path, task="detect")
        
        # 첫 번째 추론은 초기 로딩(GPU/NPU 셋업)으로 인해 오래 걸리므로 제외용으로 한 번 실행
        model.predict(source=TEST_IMAGE, conf=0.1, verbose=False)
        
        # 3. 평균 레이턴시 및 신뢰도 측정 (30회 반복)
        iterations = 30
        latencies = []
        confidence_avg = 0
        detected_count = 0
        
        for i in range(iterations):
            start_t = time.time()
            res = model.predict(source=TEST_IMAGE, conf=0.1, verbose=False)
            latencies.append(time.time() - start_t)
            
            # 첫 번째 감지된 객체의 신뢰도 추출
            if len(res) > 0 and len(res[0].boxes) > 0:
                conf = float(res[0].boxes.conf[0])
                confidence_avg += conf
                detected_count += 1
                
        avg_latency = (sum(latencies) / iterations) * 1000  # ms로 변환
        avg_conf = (confidence_avg / detected_count) * 100 if detected_count > 0 else 0
        
        results.append({
            "Model": name,
            "Size": f"{size_mb:.1f}",
            "Latency": f"{avg_latency:.1f}",
            "Confidence": f"{avg_conf:.1f}" if avg_conf > 0 else "미감지"
        })
    except Exception as e:
        print(f"❌ {name} 테스트 중 오류 발생: {e}")

print("\n" + "=" * 50)
print("📊 벤치마크 최종 결과")
print("=" * 50)
print(f"{'모델 형식':<15} | {'용량(MB)':<8} | {'속도(ms)':<10} | {'신뢰도(%)'}")
print("-" * 50)
for r in results:
    print(f"{r['Model']:<15} | {r['Size']:<8} | {r['Latency']:<10} | {r['Confidence']}")
print("=" * 50)
print("\n✅ 벤치마킹이 완료되었습니다. 이 결과를 바탕으로 benchmark_results.md를 작성합니다.")
