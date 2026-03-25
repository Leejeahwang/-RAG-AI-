"""
오프라인 음성 안내 (TTS) 모듈 (종화님 담당)

LLM이 생성한 대응 지침을 음성으로 읽어줍니다.
pip install pyttsx3
"""


def speak(text, lang="ko"):
    """
    텍스트를 음성으로 출력합니다.

    Args:
        text: 읽어줄 텍스트
        lang: 언어 코드

    TODO (종화님):
        1. pyttsx3 엔진 초기화 및 한국어 음성 설정
        2. 음성 속도/볼륨 조절
        3. 긴급도에 따른 음성 톤 변경 (Level 4+ 는 빠르게)
        4. 다국어 지원 (한국어/영어)
    """
    print(f"🗣️ [TTS 시뮬레이션] {text}")
