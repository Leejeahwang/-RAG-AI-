"""Check boot-time audio without blocking monitoring, then run main --service."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def select_sink(sinks, requested=None, default=None):
    names = [sink['name'] for sink in sinks if isinstance(sink, dict) and isinstance(sink.get('name'), str)]
    if requested:
        return requested if requested in names else None
    available = [name for name in names if name != 'auto_null']
    return default if default in available else next(iter(available), None)


def prepare_audio(driver, timeout=5):
    deadline = time.monotonic() + timeout
    os.environ['SDL_AUDIODRIVER'] = 'pulseaudio' if driver == 'pulse' else 'alsa'
    if driver == 'pulse' and not shutil.which('pactl'):
        print('[서비스] pactl이 없어 오디오 사전 확인을 생략합니다. 감시는 시작합니다.', flush=True)
        return False
    print(f'[서비스] 오디오 출력 확인: {driver}', flush=True)
    while time.monotonic() < deadline:
        if driver == 'alsa':
            if any(os.access(path, os.R_OK | os.W_OK) for path in Path('/dev/snd').glob('pcm*p')):
                return True
        else:
            try:
                sinks = subprocess.run(['pactl', '-f', 'json', 'list', 'sinks'],
                    capture_output=True, text=True, timeout=1, check=True)
                default = subprocess.run(['pactl', 'get-default-sink'],
                    capture_output=True, text=True, timeout=1, check=True).stdout.strip()
                selected = select_sink(json.loads(sinks.stdout), os.getenv('PULSE_SINK'), default)
                if selected:
                    # Do not pin an auto-selected sink: retain the same server
                    # default policy as manual main.py, including remote audio.
                    if not os.getenv('PULSE_SINK') and selected != default:
                        os.environ['PULSE_SINK'] = selected
                    policy = '지정 출력' if os.getenv('PULSE_SINK') else '서버 기본 출력 사용'
                    print(f'[서비스] 음성 출력 장치: {selected} ({policy})', flush=True)
                    return True
            except (subprocess.SubprocessError, ValueError, TypeError, KeyError):
                pass
        time.sleep(1)
    print('[서비스] 오디오 출력을 아직 확인하지 못했지만 감시는 시작합니다. '
          '음성 재생 시 다시 연결하며, 출력 장치·PipeWire 상태를 확인하세요.', flush=True)
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', choices=('pulse', 'alsa'), default='pulse')
    args = parser.parse_args(argv)
    if sys.platform != 'linux':
        parser.error('이 실행 도구는 라즈베리파이/Linux용입니다.')
    os.chdir(ROOT)
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    prepare_audio(args.audio)
    os.execv(sys.executable, [sys.executable, '-u', str(ROOT/'main.py'), '--service'])


if __name__ == '__main__':
    main()
