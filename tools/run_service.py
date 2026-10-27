"""Prepare boot-time local audio, then replace this process with main --service."""
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
    # A boot service must not silently send the building's announcements to RDP.
    physical = [name for name in names if name.startswith(('alsa_output.', 'bluez_output.'))]
    return default if default in physical else next(iter(physical), None)


def prepare_audio(driver, timeout=45):
    deadline = time.monotonic() + timeout
    if driver == 'pulse' and not shutil.which('pactl'):
        raise RuntimeError('pactl이 없습니다. pulseaudio-utils 설치 또는 --audio alsa를 확인하세요.')
    print(f'[서비스] 로컬 오디오 준비 대기: {driver}', flush=True)
    while time.monotonic() < deadline:
        if driver == 'alsa':
            if any(os.access(path, os.R_OK | os.W_OK) for path in Path('/dev/snd').glob('pcm*p')):
                os.environ['SDL_AUDIODRIVER'] = 'alsa'
                return
        else:
            try:
                sinks = subprocess.run(['pactl', '-f', 'json', 'list', 'sinks'],
                    capture_output=True, text=True, timeout=3, check=True)
                default = subprocess.run(['pactl', 'get-default-sink'],
                    capture_output=True, text=True, timeout=3, check=True).stdout.strip()
                selected = select_sink(json.loads(sinks.stdout), os.getenv('PULSE_SINK'), default)
                if selected:
                    os.environ['SDL_AUDIODRIVER'] = 'pulseaudio'
                    os.environ['PULSE_SINK'] = selected
                    print(f'[서비스] 음성 출력 장치: {selected}', flush=True)
                    return
            except (subprocess.SubprocessError, ValueError, TypeError, KeyError):
                pass
        time.sleep(1)
    raise RuntimeError('로컬 오디오 준비 시간 초과. 스피커·audio 그룹·PipeWire 상태를 확인하세요.')


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
