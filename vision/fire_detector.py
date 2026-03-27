"""
화재/연기 영상 판별 AI 모듈 (규태님 담당)

카메라로 촬영한 프레임에서 불꽃이나 연기를 감지합니다.
Phase 2: Roboflow Object Detection AI 적용 (fire-smoke-mx4z8/1)
"""

import os
from roboflow import Roboflow

# ----------------------------------------------------
# 팀장님(제황/규태) 발급 API Key 및 모델 설정
# ----------------------------------------------------
ROBOFLOW_API_KEY = "TEKa7OkOyop4SxpnZDbR"
OVERLAP_THRESHOLD = 30
CONFIDENCE_THRESHOLD = 40  # 40% 이상의 확신이 있을 때만 화재로 간주

try:
    # 파이썬 시작 시 Roboflow 클라이언트를 미리 초기화 (딜레이 최소화)
    rf = Roboflow(api_key=ROBOFLOW_API_KEY)
    # Universe에 등록된 공개 워크스페이스 모델 불러오기
    project = rf.workspace("latifa-sassi-zqgnz").project("fire-smoke-mx4z8")
    model = project.version(1).model
    ROBOFLOW_READY = True
except Exception as e:
    print(f"❌ [에러] Roboflow 초기화 실패 (API 키나 인터넷 연결을 확인하세요): {e}")
    ROBOFLOW_READY = False

def detect_fire(image_path):
    """
    이미지에서 화재(불꽃/연기)를 감지합니다.

    Args:
        image_path: 분석할 이미지 파일 경로

    Returns:
        dict: {
            "fire_detected": bool,
            "confidence": float (0.0~1.0),
            "description": str (상황 설명)
        }
    """
    print(f"📷 [Vision AI] Roboflow 모델로 화재/연기 정밀 분석 중: {image_path}")

    if not ROBOFLOW_READY:
        return {
            "fire_detected": False,
            "confidence": 0.0,
            "description": "Roboflow 모델이 로드되지 않아 분석할 수 없습니다."
        }

    if not os.path.exists(image_path):
        return {
            "fire_detected": False,
            "confidence": 0.0,
            "description": "이미지 파일을 읽어올 수 없습니다."
        }

    try:
        # 모델 예측 (이미지를 로보플로우 API로 전송하여 결과를 분석)
        prediction = model.predict(image_path, confidence=CONFIDENCE_THRESHOLD, overlap=OVERLAP_THRESHOLD).json()
        
        predictions_list = prediction.get("predictions", [])
        
        if not predictions_list:
            return {
                "fire_detected": False,
                "confidence": 0.0,
                "description": "화재나 연기 객체가 감지되지 않았습니다. (안전 구역)"
            }

        # 감지된 객체(불/연기) 분석
        max_conf = 0.0
        detected_classes = set()

        for pred in predictions_list:
            # 예: {"class": "fire", "confidence": 0.85, ...}
            conf = pred.get("confidence", 0.0)
            cls = pred.get("class", "unknown").upper()
            
            detected_classes.add(cls)
            if conf > max_conf:
                max_conf = conf

        classes_str = ", ".join(detected_classes) # 예: "FIRE, SMOKE"

        return {
            "fire_detected": True,
            "confidence": round(max_conf, 2),
            "description": f"🚨 위험 감지! 객체: [{classes_str}] (AI 확신도: {max_conf*100:.1f}%)"
        }

    except Exception as e:
        return {
            "fire_detected": False,
            "confidence": 0.0,
            "description": f"AI 분석 중 통신/처리 오류 발생: {str(e)}"
        }
