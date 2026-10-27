"""Install an Edge Saver user service on Linux. Run as the normal Pi user.

python tools/install_autostart.py --start
The installer never writes .env or runs the application as root.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SERVICE = 'edge-saver.service'


def _quote(value, command=False):
    value = str(value)
    if any(char in value for char in ('\n', '\r', '\x00')):
        raise ValueError('서비스 경로에 줄바꿈·NUL을 사용할 수 없습니다.')
    value = value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    if command:
        value = value.replace('$', '$$')
    return '"' + value + '"'


def build_unit(project, python, audio='pulse', sink=None):
    if audio not in ('pulse', 'alsa'):
        raise ValueError('unsupported audio driver')
    lines = ['[Unit]', 'Description=Edge Saver fire detection and voice guidance',
             'StartLimitIntervalSec=0']
    if audio == 'pulse':
        lines += ['Wants=pipewire.service pipewire-pulse.service wireplumber.service',
                  'After=pipewire.service pipewire-pulse.service wireplumber.service']
    lines += ['', '[Service]', 'Type=exec', 'WorkingDirectory=' + _quote(project),
              'ExecStart=' + _quote(python, True) + ' -u ' +
              _quote(Path(project)/'tools'/'run_service.py', True) + ' --audio ' + audio,
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
    for tool in ('systemctl', 'loginctl') + (('pactl',) if args.audio == 'pulse' else ()):
        if not shutil.which(tool):
            parser.error(f'{tool}이 없습니다. 설치 환경과 오디오 방식을 확인하세요.')
    info = subprocess.run([str(python), '-c',
        'import sys,json; print(json.dumps([list(sys.version_info[:2]),sys.prefix!=sys.base_prefix]))'],
        check=True, capture_output=True, text=True)
    if json.loads(info.stdout) != [[3, 11], True]:
        parser.error('--python에 Python 3.11 가상환경의 bin/python을 지정하세요.')
    # Check the user's manager before writing a unit or asking sudo for linger.
    subprocess.run(['systemctl', '--user', 'show-environment'], check=True, stdout=subprocess.DEVNULL)
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
    base = Path(os.getenv('XDG_CONFIG_HOME', str(Path.home()/'.config')))/'systemd'/'user'
    base.mkdir(parents=True, exist_ok=True)
    target = base/SERVICE
    if target.exists() and target.read_text(encoding='utf-8') != unit:
        shutil.copy2(target, target.with_suffix('.service.bak'))
    target.write_text(unit, encoding='utf-8')
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', SERVICE], check=True)
    if args.start:
        subprocess.run(['systemctl', '--user', 'restart', SERVICE], check=True)
    print(f'부팅 자동 실행 등록 완료: {target}')
    print('실행 준비 완료 여부: journalctl --user -u edge-saver.service -f')
    print('수동 실행 전 중지: systemctl --user stop edge-saver.service')


if __name__ == '__main__':
    main()
