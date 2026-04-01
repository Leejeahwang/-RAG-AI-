from voice.tts import TTSHelper
import time

def test_tts():
    print("🔊 TTS 독립 테스트를 시작합니다.")
    tts = TTSHelper()
    
    print("\n1. 모든 사용 가능한 음성 목록:")
    tts.list_voices()
    
    print("\n2. 한국어 음성 출력 테스트 중...")
    test_text = "안녕하세요. 오프라인 재난 안전 가이드 시스템 엣지 세이버입니다. 지금 목소리가 잘 들리시나요?"
    tts.speak(test_text)
    
    print("\n3. 테스트 종료. 소리가 들리지 않았다면 시스템 볼륨이나 스피커 설정을 확인해 주세요.")

if __name__ == "__main__":
    test_tts()
