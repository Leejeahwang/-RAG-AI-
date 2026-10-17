"""One short API synthesis probe; saves WAV without playing or logging credentials."""
import argparse
from pathlib import Path
import sys
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from voice.gemini_tts import synthesize_to_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--text', default='안녕하세요. 한국어 음성 안내 시험입니다.')
    parser.add_argument('--output', type=Path, default=Path('gemini_tts_test.wav'))
    args = parser.parse_args()
    if args.output.exists():
        parser.error('출력 파일이 이미 있습니다. 다른 --output 경로를 지정하세요.')
    started = time.perf_counter()
    try:
        synthesize_to_file(args.text, args.output)
        with wave.open(str(args.output), 'rb') as audio:
            duration = audio.getnframes()/audio.getframerate()
            rate = audio.getframerate()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) and str(exc).startswith('Gemini TTS HTTP ') else type(exc).__name__
        print(f'[Gemini TTS] 실패: {reason}')
        return 1
    print(f'[Gemini TTS] 성공: 모델={config.GEMINI_TTS_MODEL}, 요청={time.perf_counter()-started:.2f}초, 음성={duration:.2f}초, {rate}Hz')
    print(f'저장: {args.output.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
