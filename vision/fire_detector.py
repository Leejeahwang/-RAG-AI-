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

# 지원하는 모델 확장자 및 디렉토리
POSSIBLE_MODELS = [
    os.path.join(MODEL_DIR, "fire_smoke_int8_openvino_model")          # OpenVINO INT8 (라즈베리파이 5 CPU 최적화)
]

model = None
CONFIDENCE_THRESHOLD = 0.40  # 40% 이상의 확신이 있을 때만 화재로 간주

# 가장 가볍고 최적화된 포맷부터 순서대로 로드를 시도합니다.
for m_path in POSSIBLE_MODELS:
    if os.path.exists(m_path):
        try:
            print(f"🔄 [Vision AI] 모델 로드 시도 중: {os.path.basename(m_path)}")
            loaded_model = YOLO(m_path, task="detect")
            model = loaded_model
            print(f"✅ [Vision AI] 오프라인 화재 모델 로드 완료: {os.path.basename(m_path)}")
            break
        except Exception as e:
            print(f"⚠️ [경고] '{os.path.basename(m_path)}' 로드 실패, 다음 옵션으로 전환합니다. 에러: {e}")

if model is None:
    print(f"❌ [에러] 어떠한 모델 파일도 로드하지 못했습니다. {MODEL_DIR} 디렉토리의 모델 파일들을 확인하세요.")

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
