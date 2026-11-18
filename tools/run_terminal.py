"""Open the existing interactive main.py in LXTerminal; no service-mode logic."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def terminal_command(terminal, python, project):
    script = Path(project)/'tools'/'run_terminal.py'
    command = shlex.join([str(python), '-u', str(script), '--inside'])
    return [terminal, '--no-remote', '--title=Edge Saver', '--working-directory=' + str(project), '--command=' + command]


def run_inside():
    import fcntl
    runtime = ROOT/'.runtime'
    runtime.mkdir(exist_ok=True)
    with (runtime/'terminal-main.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Edge Saver 터미널 실행이 이미 진행 중입니다.', flush=True)
            return 0
        # Keep the lock in this parent until interactive main exits. Multiple
        # desktop/RDP logins must not open competing copies on the same camera.
        try:
            return subprocess.run([sys.executable, '-u', str(ROOT/'main.py')], cwd=ROOT).returncode
        except KeyboardInterrupt:
            return 130


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if sys.platform != 'linux':
        parser.error('라즈베리파이/Linux 데스크톱용입니다.')
    if args.inside:
        return run_inside()
    if not (os.getenv('DISPLAY') or os.getenv('WAYLAND_DISPLAY')):
        parser.error('데스크톱 세션에서 실행하세요. 로그인 전에는 터미널 창을 열 수 없습니다.')
    terminal = shutil.which('lxterminal')
    if not terminal:
        parser.error('lxterminal이 없습니다. Raspberry Pi OS의 LXTerminal 설치를 확인하세요.')
    subprocess.Popen(terminal_command(terminal, sys.executable, ROOT), cwd=ROOT, start_new_session=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
