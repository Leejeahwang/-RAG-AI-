"""
화재/연기 영상 판별 AI 모듈 (규태님 담당)

카메라로 촬영한 프레임에서 불꽃이나 연기를 감지합니다.
Phase 1: 시뮬레이션 (항상 False 반환)
Phase 2: 실제 Vision AI 모델 적용 (OpenCV + 경량 모델)
"""


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

    TODO (규태님):
        1. 화재/연기 감지용 경량 CNN 모델 조사 및 선택
           - YOLOv8-nano (불꽃 감지 파인튜닝)
           - 또는 OpenCV 색상 기반 불꽃 감지 (HSV 필터링)
        2. 모델 로드 및 추론 파이프라인 구현
        3. 감지 결과를 dict 형태로 반환
    """
    # Phase 1: 시뮬레이션 모드
    print(f"📷 [Vision AI] 이미지 분석 중: {image_path}")
    print("   ⚠️ 현재 시뮬레이션 모드 (Phase 2에서 실제 모델 적용)")

    return {
        "fire_detected": False,
        "confidence": 0.0,
        "description": "시뮬레이션 모드 - 화재 미감지",
    }
