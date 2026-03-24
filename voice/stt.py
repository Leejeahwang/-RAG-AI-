"""
오프라인 STT (Speech-to-Text) 모듈 (종화님 담당)

Phase 1~2 작업 내용:
- vosk 한국어 모델 기반 오프라인 음성 인식
- 웨이크워드("세이버") 감지 기능
- 마이크 입력 → 텍스트 변환

설치:
    pip install vosk sounddevice

한국어 모델 다운로드:
    https://alphacephei.com/vosk/models
    → vosk-model-small-ko-0.22 (경량) 또는 vosk-model-ko-0.22 (고정밀)
"""

# TODO (종화님):
# 1. vosk 한국어 모델 로드
# 2. 마이크 입력 스트리밍 처리 (sounddevice)
# 3. 웨이크워드("세이버") 감지 로직 구현


def listen() -> str:
    """
    마이크에서 음성을 인식하여 텍스트로 변환합니다.

    Returns:
        str: 인식된 텍스트

    TODO (종화님):
        1. vosk.Model() 로 한국어 모델 로드
        2. sounddevice로 마이크 입력 캡처
        3. 인식된 텍스트 반환
    """
    raise NotImplementedError("STT 모듈이 아직 구현되지 않았습니다.")


def detect_wakeword(text: str) -> bool:
    """
    웨이크워드("세이버")가 포함되어 있는지 확인합니다.

    Args:
        text: 인식된 텍스트

    Returns:
        bool: 웨이크워드 포함 여부

    TODO (종화님):
        - "세이버", "세이 버" 등 다양한 변형도 감지하도록 구현
    """
    raise NotImplementedError("웨이크워드 감지가 아직 구현되지 않았습니다.")
