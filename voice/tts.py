import pyttsx3
import platform
import threading

class TTSHelper:
    """
    TTSHelper: 오프라인 한국어 음성 합성(TTS) 모듈
    =============================================
    - pyttsx3 기반 (Windows: SAPI5, Linux: eSpeak)
    - 재난 안전 RAG 시스템에 최적화
    - 속도, 볼륨 조절 및 한국어 음성 자동 선택 지원
    """
    def __init__(self, rate=180, volume=1.0):
        try:
            self.engine = pyttsx3.init()
            self._set_korean_voice()
            self.engine.setProperty('rate', rate)
            self.engine.setProperty('volume', volume)
            self.lock = threading.Lock()
            print("[TTS] 초기화 성공.")
        except Exception as e:
            print(f"[TTS] 초기화 실패: {e}")
            self.engine = None

    def _set_korean_voice(self):
        """시스템에서 한국어 음성을 자동으로 찾아 설정"""
        if not self.engine:
            return
            
        voices = self.engine.getProperty('voices')
        
        # 한국어 음성 식별자 리스트
        korean_identifiers = ["ko_KR", "korean", "heami", "yumi", "kr"]
        
        for voice in voices:
            name = voice.name.lower()
            v_id = voice.id.lower()
            
            if any(k in name or k in v_id for k in korean_identifiers):
                self.engine.setProperty('voice', voice.id)
                print(f"[TTS] 선택된 음성: {voice.name}")
                return
        
        print("[TTS] 경고: 한국어 음성을 찾을 수 없습니다. 시스템 기본값을 사용합니다.")

    def speak(self, text):
        """텍스트를 음성으로 합성하여 출력 (동기 방식)"""
        if not self.engine or not text:
            return
            
        with self.lock:
            print(f"[TTS] 출력 중: {text}")
            self.engine.say(text)
            self.engine.runAndWait()

    def speak_async(self, text):
        """별도 스레드에서 음성을 합성하여 출력 (비동기 방식)"""
        t = threading.Thread(target=self.speak, args=(text,))
        t.daemon = True
        t.start()

    def list_voices(self):
        """시스템에서 사용 가능한 모든 음성 목록 출력"""
        if not self.engine:
            return
        voices = self.engine.getProperty('voices')
        print("\n사용 가능한 음성 목록:")
        for i, voice in enumerate(voices):
            print(f"{i}: {voice.name} [{voice.id}] - 언어: {voice.languages}")

if __name__ == "__main__":
    # 자체 테스트 코드
    tts = TTSHelper()
    tts.list_voices()
    
    test_text = "안녕하세요. 재난 안전 길잡이 세이버입니다. 무엇을 도와드릴까요?"
    tts.speak(test_text)
