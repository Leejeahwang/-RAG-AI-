"""Switch to desktop-login autostart of the existing interactive main.py."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.install_autostart import connect_user_manager, SERVICE

DESKTOP_FILE = 'edge-saver-terminal.desktop'


def desktop_argument(value):
    value = str(value)
    if any(char in value for char in ('\n', '\r', '\x00')):
        raise ValueError('자동 실행 경로에 줄바꿈·NUL을 사용할 수 없습니다.')
    # Desktop string unescaping precedes Exec argument unquoting.
    value = ''.join('\\' + char if char in ('"', '`', '$', '\\') else char for char in value)
    return '"' + value.replace('\\', '\\\\').replace('%', '%%') + '"'


def build_desktop(project, python):
    launcher = PurePosixPath(project)/'tools'/'run_terminal.py'
    return '\n'.join(['[Desktop Entry]', 'Type=Application', 'Name=Edge Saver (Terminal)',
        'Comment=Run interactive fire detection and voice guidance in LXTerminal',
        'Exec=' + desktop_argument(python) + ' -u ' + desktop_argument(launcher),
        'Terminal=false', 'Hidden=false', 'X-GNOME-Autostart-enabled=true', ''])


def stop_background_service(config_home, uid):
    if (config_home/'systemd'/'user'/SERVICE).is_file():
        env = connect_user_manager(uid)
        subprocess.run(['systemctl', '--user', 'disable', '--now', SERVICE], env=env, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', help='Python 3.11 가상환경 bin/python')
    parser.add_argument('--start', action='store_true', help='현재 데스크톱에서도 지금 터미널 실행')
    args = parser.parse_args(argv)
    if sys.platform != 'linux' or os.geteuid() == 0:
        parser.error('라즈베리파이 데스크톱의 일반 사용자로 실행하세요. sudo를 붙이지 않습니다.')
    if not shutil.which('lxterminal'):
        parser.error('lxterminal이 없습니다. Raspberry Pi OS의 LXTerminal 설치를 확인하세요.')
    if args.start and not (os.getenv('DISPLAY') or os.getenv('WAYLAND_DISPLAY')):
        parser.error('--start는 데스크톱 터미널에서 실행하세요.')
    candidates = [ROOT/'.venv-py311'/'bin'/'python', ROOT/'.venv'/'bin'/'python']
    python = Path(args.python).expanduser().absolute() if args.python else next(
        (path for path in candidates if path.is_file()), Path(sys.executable).absolute())
    info = subprocess.run([str(python), '-c',
        'import sys,json; print(json.dumps([list(sys.version_info[:2]),sys.prefix!=sys.base_prefix]))'],
        check=True, capture_output=True, text=True)
    if json.loads(info.stdout) != [[3, 11], True]:
        parser.error('--python에 Python 3.11 가상환경 bin/python을 지정하세요.')
    content = build_desktop(ROOT, python)
    config_home = Path(os.getenv('XDG_CONFIG_HOME', str(Path.home()/'.config')))
    stop_background_service(config_home, os.getuid())
    directory = config_home/'autostart'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/DESKTOP_FILE
    if target.exists() and target.read_text(encoding='utf-8') != content:
        shutil.copy2(target, target.with_suffix('.desktop.bak'))
    target.write_text(content, encoding='utf-8')
    print(f'터미널 자동 실행 등록 완료: {target}')
    print('기존 백그라운드 서비스는 등록돼 있었다면 중지·해제했습니다.')
    print('데스크톱 로그인 때 기존 main.py가 터미널에서 실행됩니다. 전원 부팅 시에는 데스크톱 자동 로그인이 필요합니다.')
    if args.start:
        subprocess.run([str(python), str(ROOT/'tools'/'run_terminal.py')], check=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        print(f'터미널 자동 실행 등록 실패: {exc}', file=sys.stderr)
        sys.exit(1)
