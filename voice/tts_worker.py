import pyttsx3
import sys
import platform
import subprocess
import wave

def get_voice_id(engine, lang):
    """언어 코드에 맞는 목소리 ID 반환 (Windows용)"""
    voices = engine.getProperty('voices')
    lang_map = {
        'ko': ['ko_KR', 'korean', 'heami', 'yumi'],
        'en': ['en_US', 'english', 'zira', 'david'],
        'ja': ['ja_JP', 'japanese', 'haruka', 'ayumi'],
        'zh': ['zh_CN', 'chinese', 'huihui', 'yaoyao']
    }
    
    target_keywords = [key.lower() for key in lang_map.get(lang, ['ko_KR'])]
    
    for voice in voices:
        name = voice.name.lower()
        v_id = voice.id.lower()
        languages = [item.decode('utf-8', errors='ignore') if isinstance(item, bytes) else str(item)
                     for item in getattr(voice, 'languages', [])]
        if any(item.lstrip('\x00\x01\x02\x03\x04\x05').lower().replace('_', '-').split('-')[0] == lang
               for item in languages):
            return voice.id
        if any(k in name or k in v_id for k in target_keywords):
            return voice.id
    return None

def speak(text, lang='ko', rate=180, volume=1.0, output_path=None):
    try:
        current_os = platform.system()
        
        # 1. Windows 환경 (SAPI5)
        if current_os == 'Windows':
            engine = pyttsx3.init('sapi5')
            voice_id = get_voice_id(engine, lang)
            if lang == 'ko' and voice_id is None:
                raise RuntimeError('Korean system voice unavailable')
            if voice_id:
                engine.setProperty('voice', voice_id)
            
            engine.setProperty('rate', rate)
            engine.setProperty('volume', volume)
            if output_path:
                engine.save_to_file(text, output_path)
            else:
                engine.say(text)
            engine.runAndWait()
            engine.stop()
            
        else:
            engine = pyttsx3.init()
            voice_id = get_voice_id(engine, lang)
            if lang == 'ko' and voice_id is None:
                raise RuntimeError('Korean system voice unavailable')
            if voice_id:
                engine.setProperty('voice', voice_id)
            engine.setProperty('rate', rate)
            engine.setProperty('volume', volume)
            if output_path:
                engine.save_to_file(text, output_path)
            else:
                engine.say(text)
            engine.runAndWait()
            engine.stop()

        if output_path:
            # Some driver errors are handled internally; validate the output
            # so the parent cannot report successful synthesis without audio.
            with wave.open(output_path, 'rb') as audio:
                if audio.getnframes() == 0:
                    raise RuntimeError('System TTS produced an empty WAV file')

    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"TTS Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    # 인자: [텍스트] [언어코드]
    # 예: python tts_worker.py "Hello" "en"
    if len(sys.argv) > 1:
        text = sys.argv[1]
        lang = sys.argv[2] if len(sys.argv) > 2 else 'ko'
        rate = int(sys.argv[3]) if len(sys.argv) > 3 else 180
        volume = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
        output_path = None
        if len(sys.argv) > 5:
            if len(sys.argv) != 7 or sys.argv[5] != '--output':
                print('TTS Error: invalid output arguments', file=sys.stderr)
                sys.exit(1)
            output_path = sys.argv[6]
        speak(text, lang, rate, volume, output_path=output_path)
