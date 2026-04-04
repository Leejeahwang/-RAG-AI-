import subprocess
import platform
import os
import sys

class TTSHelper:
    """
    TTSHelper: 다국어 지원 오프라인 음성 합성(TTS) 모듈 (프로세스 분리 방식)
    ======================================================================
    - Windows(SAPI5) 및 Linux(espeak-ng) 크로스 플랫폼 지원
    - 한국어(ko), 영어(en), 일본어(ja), 중국어(zh) 다국어 지원
    - subprocess.Popen을 이용하여 즉각적인 중단(kill) 보장
    """
    def __init__(self, rate=180, volume=1.0):
        self._rate = rate
        self._volume = volume
        self._active_process = None
        
        # tts_worker.py 파일 경로 설정
        self._worker_path = os.path.join(os.path.dirname(__file__), "tts_worker.py")
        print(f"[TTS] 다국어 음성 엔진 준비 완료 ({platform.system()} 지원).")

    def speak(self, text, lang='ko'):
        """텍스트를 별도 프로세스에서 해당 언어의 음성으로 출력"""
        if not text: return
        
        # 이미 실행 중인 프로세스가 있다면 즉시 종료
        self.stop()
        
        try:
            # tts_worker.py를 새로운 프로세스로 실행
            # 인자: [텍스트] [언어코드]
            creationflags = 0
            if platform.system() == "Windows":
                creationflags = subprocess.CREATE_NO_WINDOW
                
            self._active_process = subprocess.Popen(
                [sys.executable, self._worker_path, text, lang],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
        except Exception as e:
            print(f"[TTS] 음성 프로세스 생성 실패: {e}")

    def speak_async(self, text, lang='ko'):
        """비동기 방식으로 호환성 유지"""
        self.speak(text, lang)

    def stop(self):
        """현재 진행 중인 음성 프로세스를 강제로 즉각 종료"""
        if self._active_process:
            try:
                self._active_process.kill()
                self._active_process.wait(timeout=0.1)
            except Exception:
                pass
            finally:
                self._active_process = None

if __name__ == "__main__":
    # 자체 테스트 코드
    import time
    tts = TTSHelper()
    
    print("Test: English")
    tts.speak("Hello, I am Edge Saver. Nice to meet you.", "en")
    time.sleep(3)
    
    print("Test: Japanese")
    tts.speak("こんにちは、エッジセ이버です。", "ja")
    time.sleep(3)
    
    print("Test: Korean")
    tts.speak("안녕하세요, 엣지 세이버입니다.", "ko")
    time.sleep(3)
