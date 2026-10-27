"""Install an Edge Saver user service on Linux. Run as the normal Pi user.

python tools/install_autostart.py --start
The installer never writes .env or runs the application as root.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SERVICE = 'edge-saver.service'


def connect_user_manager(uid):
    """xrdp may export a private session bus; use the boot user manager's bus."""
    env = os.environ.copy()
    env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'
    env['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path=/run/user/{uid}/bus'
    probe = ['systemctl', '--user', 'show-environment']
    def available():
        return subprocess.run(probe, env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, text=True, timeout=15).returncode == 0
    if not available():
        print('[설치] 부팅용 사용자 서비스 관리자를 시작합니다.', flush=True)
        subprocess.run(['sudo', 'systemctl', 'start', f'user@{uid}.service'], check=True)
        if not available():
            raise RuntimeError('사용자 systemd 연결 실패. dbus-user-session 설치 여부와 '
                               f'systemctl status user@{uid}.service를 확인하세요. '
                               '원격 데스크톱 재연결 또는 재부팅 후 다시 시도하세요.')
    return env


def _quote(value, command=False):
    value = str(value)
    if any(char in value for char in ('\n', '\r', '\x00')):
        raise ValueError('서비스 경로에 줄바꿈·NUL을 사용할 수 없습니다.')
    value = value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    if command:
        value = value.replace('$', '$$')
    return '"' + value + '"'


def _working_directory(value):
    # Unlike ExecStart, WorkingDirectory's parser does not remove quotes.
    # Spaces are part of this single path value, not shell argument separators.
    value = str(value)
    if not value.startswith('/') or any(char in value for char in ('\n', '\r', '\x00', '\\')):
        raise ValueError('WorkingDirectory에는 Linux 절대 경로를 사용하세요.')
    return value.replace('%', '%%')


def verify_unit(unit, manager_env):
    """Let the target OS parse the complete unit before replacing its file."""
    with tempfile.TemporaryDirectory(prefix='edge-saver-unit-') as folder:
        candidate = Path(folder)/SERVICE
        candidate.write_text(unit, encoding='utf-8')
        result = subprocess.run(['systemd-analyze', '--user', 'verify', str(candidate)],
                                env=manager_env, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError('서비스 파일 검증 실패:\n' + (result.stderr or result.stdout).strip())


def build_unit(project, python, audio='pulse', sink=None):
    if audio not in ('pulse', 'alsa'):
        raise ValueError('unsupported audio driver')
    lines = ['[Unit]', 'Description=Edge Saver fire detection and voice guidance',
             'StartLimitIntervalSec=0']
    if audio == 'pulse':
        lines += ['Wants=pipewire.service pipewire-pulse.service wireplumber.service',
                  'After=pipewire.service pipewire-pulse.service wireplumber.service']
    lines += ['', '[Service]', 'Type=exec', 'WorkingDirectory=' + _working_directory(project),
              'ExecStart=' + _quote(python, True) + ' -u ' +
              _quote(PurePosixPath(project)/'tools'/'run_service.py', True) + ' --audio ' + audio,
              'Environment=PYTHONUNBUFFERED=1', 'Environment=XDG_RUNTIME_DIR=%t',
              'Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus']
    if audio == 'pulse':
        lines += ['Environment=PULSE_SERVER=unix:%t/pulse/native']
    if sink:
        lines += ['Environment=' + _quote('PULSE_SINK=' + sink)]
    else:
        lines += ['UnsetEnvironment=PULSE_SINK']
    lines += ['StandardInput=null', 'StandardOutput=journal', 'StandardError=journal',
              'Restart=on-failure', 'RestartSec=10', 'TimeoutStopSec=30',
              'KillMode=control-group', '', '[Install]', 'WantedBy=default.target', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', help='Python 3.11 가상환경의 bin/python 경로')
    parser.add_argument('--audio', choices=('pulse', 'alsa'), default='pulse')
    parser.add_argument('--pulse-sink', help='pactl list short sinks에 표시되는 출력 장치 이름')
    parser.add_argument('--start', action='store_true', help='등록한 서비스를 지금 시작/재시작')
    parser.add_argument('--dry-run', action='store_true', help='파일과 시스템 설정을 변경하지 않고 서비스 내용 출력')
    args = parser.parse_args(argv)
    candidates = [ROOT/'.venv-py311'/'bin'/'python', ROOT/'.venv'/'bin'/'python']
    python = Path(args.python).expanduser().absolute() if args.python else next(
        (path for path in candidates if path.is_file()), Path(sys.executable).absolute())
    unit = build_unit(ROOT, python, args.audio, args.pulse_sink)
    if args.dry_run:
        print(unit)
        return
    if sys.platform != 'linux' or os.geteuid() == 0:
        parser.error('라즈베리파이의 일반 사용자로 실행하세요. 이 스크립트 앞에 sudo를 붙이지 마세요.')
    for tool in ('systemctl', 'loginctl', 'systemd-analyze') + (('pactl',) if args.audio == 'pulse' else ()):
        if not shutil.which(tool):
            parser.error(f'{tool}이 없습니다. 설치 환경과 오디오 방식을 확인하세요.')
    info = subprocess.run([str(python), '-c',
        'import sys,json; print(json.dumps([list(sys.version_info[:2]),sys.prefix!=sys.base_prefix]))'],
        check=True, capture_output=True, text=True)
    if json.loads(info.stdout) != [[3, 11], True]:
        parser.error('--python에 Python 3.11 가상환경의 bin/python을 지정하세요.')
    import pwd
    user = pwd.getpwuid(os.getuid()).pw_name
    import grp
    groups = {grp.getgrgid(gid).gr_name for gid in os.getgroups() + [os.getgid()]}
    missing = [name for name in ('audio', 'video', 'render')
               if name not in groups and any(group.gr_name == name for group in grp.getgrall())]
    if missing:
        parser.error(f"로그인 없이 장치 접근에 필요한 그룹을 확인하세요: sudo usermod -aG {','.join(missing)} {user}\n"
                     '변경 후 재부팅하고 이 설치 명령을 다시 실행하세요.')
    linger = subprocess.run(['loginctl', 'show-user', user, '-p', 'Linger', '--value'],
                            check=True, capture_output=True, text=True).stdout.strip()
    if linger != 'yes':
        subprocess.run(['sudo', 'loginctl', 'enable-linger', user], check=True)
    manager_env = connect_user_manager(os.getuid())
    verify_unit(unit, manager_env)
    base = Path(os.getenv('XDG_CONFIG_HOME', str(Path.home()/'.config')))/'systemd'/'user'
    base.mkdir(parents=True, exist_ok=True)
    target = base/SERVICE
    if target.exists() and target.read_text(encoding='utf-8') != unit:
        shutil.copy2(target, target.with_suffix('.service.bak'))
    target.write_text(unit, encoding='utf-8')
    subprocess.run(['systemctl', '--user', 'daemon-reload'], env=manager_env, check=True)
    subprocess.run(['systemctl', '--user', 'reset-failed', SERVICE], env=manager_env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    subprocess.run(['systemctl', '--user', 'enable', SERVICE], env=manager_env, check=True)
    if args.start:
        subprocess.run(['systemctl', '--user', 'restart', SERVICE], env=manager_env, check=True)
    print(f'부팅 자동 실행 등록 완료: {target}')
    print('실행 준비 완료 여부: journalctl --user -u edge-saver.service -f')
    print('수동 실행 전 중지: systemctl --user stop edge-saver.service')


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        print(f'자동 실행 등록 실패: {exc}', file=sys.stderr)
        sys.exit(1)
