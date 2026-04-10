"""
화재/연기 영상 판별 AI 모듈 (로컬 오프라인 YOLOv8 버전)

카메라로 촬영한 프레임에서 불꽃이나 연기를 감지합니다.
Phase 3: 인터넷 연결 없이 라즈베리파이 로컬에서 ultralytics 모델 구동
"""

import os
try:
    from ultralytics import YOLO
except ImportError:
    print("❌ [에러] ultralytics 라이브러리가 설치되지 않았습니다. 터미널에서 'pip install ultralytics' 를 실행하세요.")

# 로컬 모델 경로 설정 (vision/models 폴더)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")

# 지원하는 모델 확장자 (tflite, onnx, ncnn 포맷으로 변환했을 경우 우선 사용)
POSSIBLE_MODELS = [
    os.path.join(MODEL_DIR, "fire_smoke.ncnn"),   # 가장 빠름 (라즈베리파이/NPU 최적화)
    os.path.join(MODEL_DIR, "fire_smoke.tflite"), # 빠름
    os.path.join(MODEL_DIR, "fire_smoke.onnx"),   # 빠름 (PC/라즈베리파이 멀티플랫폼 표준, FP16 양자화 적용 완료)
    os.path.join(MODEL_DIR, "fire_smoke.pt")      # 기본 PyTorch 포맷 (YOLOv8n 큰 용량)
]

model = None
CONFIDENCE_THRESHOLD = 0.10  # 40% 이상의 확신이 있을 때만 화재로 간주

try:
    # 가장 빠르고 가벼운 변환 포맷부터 파일이 존재하는지 찾아서 로드합니다.
    loaded_model_path = None
    for m_path in POSSIBLE_MODELS:
        if os.path.exists(m_path):
            loaded_model_path = m_path
            break
            
    if loaded_model_path:
        print(f"✅ [Vision AI] 오프라인 화재 모델 로드됨: {os.path.basename(loaded_model_path)}")
        model = YOLO(loaded_model_path)
    else:
        print(f"⚠️ [경고] 모델 파일을 찾을 수 없습니다. {MODEL_DIR} 에 'fire_smoke.pt' 모델이 존재하는지 확인하세요.")
except Exception as e:
    print(f"❌ [에러] 모델 초기화 실패: {e}")

def detect_fire(image_path):
    """
    이미지에서 오프라인으로 화재(불꽃/연기)를 감지합니다.

    Args:
        image_path: 분석할 이미지 파일 경로

    Returns:
        dict: {
            "fire_detected": bool,
            "confidence": float (0.0~1.0),
            "description": str (상황 설명)
        }
    """
    if model is None:
        return {
            "fire_detected": False,
            "confidence": 0.0,
            "description": "모델 서버가 초기화되지 않았거나 로컬 모델 파일(pt)이 없습니다."
        }

    if not os.path.exists(image_path):
        return {
            "fire_detected": False,
            "confidence": 0.0,
            "description": "이미지 파일을 읽어올 수 없습니다."
        }

    try:
        # 모델 예측 (오프라인, verbose=False로 콘솔 로그 방지)
        results = model.predict(source=image_path, conf=CONFIDENCE_THRESHOLD, save=False, verbose=False)
        
        if not results or len(results) == 0:
            return {
                "fire_detected": False,
                "confidence": 0.0,
                "description": "분석 결과가 반환되지 않았습니다."
            }
            
        result = results[0]
        boxes = result.boxes
        
        if len(boxes) == 0:
            return {
                "fire_detected": False,
                "confidence": 0.0,
                "description": "화재나 연기 객체가 감지되지 않았습니다. (안전 구역)"
            }

        # 감지된 객체 분석
        max_conf = 0.0
        detected_classes = set()
        
        # 클래스 이름 딕셔너리 (예: {0: 'fire', 1: 'smoke'})
        names = result.names 

        for box in boxes:
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            cls_name = names[cls_id].upper()
            
            detected_classes.add(cls_name)
            if conf > max_conf:
                max_conf = conf

        classes_str = ", ".join(detected_classes)

        return {
            "fire_detected": True,
            "confidence": round(max_conf, 2),
            "description": f"🚨 [로컬 감지] 위험 요소: [{classes_str}] (AI 확신도: {max_conf*100:.1f}%)"
        }

    except Exception as e:
        return {
            "fire_detected": False,
            "confidence": 0.0,
            "description": f"AI 분석 중 로컬 처리 오류 발생: {str(e)}"
        }
