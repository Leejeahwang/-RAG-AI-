"""
오프라인 TTS (Text-to-Speech) 모듈 (종화님 담당)

Phase 1~2 작업 내용:
- pyttsx3 기반 오프라인 음성 합성
- 한국어 음성 출력 (응급처치 지침 읽어주기)

설치:
    pip install pyttsx3
"""

# TODO (종화님):
# 1. pyttsx3 엔진 초기화
# 2. 한국어 음성 설정 (속도, 볼륨 조절)
# 3. 텍스트 → 음성 출력


def speak(text: str) -> None:
    """
    텍스트를 음성으로 출력합니다.

    Args:
        text: 읽어줄 텍스트 (AI 답변)

    TODO (종화님):
        1. pyttsx3.init() 엔진 생성
        2. engine.setProperty('rate', 150) 등 속도 조절
        3. engine.say(text) → engine.runAndWait()
    """
    raise NotImplementedError("TTS 모듈이 아직 구현되지 않았습니다.")
