"""
카메라 캡처 모듈 (규태님 담당)

Phase 1 작업 내용:
- OpenCV로 웹캠/카메라 프레임 캡처
- 프레임 선택 전략 (키 입력 or 일정 간격)
- 이미지 전처리 (리사이즈, 압축)
- Vision → RAG 파이프라인 연결
"""

# TODO: OpenCV 설치 후 구현
# pip install opencv-python


def capture_frame():
    """
    카메라에서 프레임을 캡처합니다.

    Returns:
        캡처된 이미지 (numpy array) 또는 None

    TODO (규태님):
        1. cv2.VideoCapture(0) 으로 웹캠 열기
        2. 프레임 캡처 및 전처리 (리사이즈 등)
        3. 캡처된 프레임 반환
    """
    raise NotImplementedError("카메라 캡처 모듈이 아직 구현되지 않았습니다.")
