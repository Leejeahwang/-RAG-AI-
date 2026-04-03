import pyttsx3
import sys
import platform
import subprocess

def get_voice_id(engine, lang):
    """언어 코드에 맞는 목소리 ID 반환 (Windows용)"""
    voices = engine.getProperty('voices')
    lang_map = {
        'ko': ['ko_KR', 'korean', 'heami', 'yumi'],
        'en': ['en_US', 'english', 'zira', 'david'],
        'ja': ['ja_JP', 'japanese', 'haruka', 'ayumi'],
        'zh': ['zh_CN', 'chinese', 'huihui', 'yaoyao']
    }
    
    target_keywords = lang_map.get(lang, ['ko_KR'])
    
    for voice in voices:
        name = voice.name.lower()
        v_id = voice.id.lower()
        if any(k in name or k in v_id for k in target_keywords):
            return voice.id
    return None

def speak(text, lang='ko', rate=180, volume=1.0):
    try:
        current_os = platform.system()
        
        # 1. Windows 환경 (SAPI5)
        if current_os == 'Windows':
            engine = pyttsx3.init('sapi5')
            voice_id = get_voice_id(engine, lang)
            if voice_id:
                engine.setProperty('voice', voice_id)
            
            engine.setProperty('rate', rate)
            engine.setProperty('volume', volume)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
            
        # 2. Linux 환경 (Raspberry Pi 등 - espeak-ng 사용)
        else:
            # espeak-ng 언어 코드 매핑
            espeak_lang_map = {
                'ko': 'ko',
                'en': 'en-us',
                'ja': 'ja',
                'zh': 'zh'
            }
            target_lang = espeak_lang_map.get(lang, 'ko')
            
            # subprocess를 통해 espeak-ng 직접 호출 (가장 확실함)
            try:
                subprocess.run(['espeak-ng', '-v', target_lang, '-s', str(rate), '-a', str(int(volume*100)), text], check=True)
            except FileNotFoundError:
                # espeak-ng가 없으면 pyttsx3 시도
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()

    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        # print(f"TTS Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    # 인자: [텍스트] [언어코드]
    # 예: python tts_worker.py "Hello" "en"
    if len(sys.argv) > 1:
        text = sys.argv[1]
        lang = sys.argv[2] if len(sys.argv) > 2 else 'ko'
        speak(text, lang)
