# Raspberry Pi 전원 켤 때 자동 실행

## 터미널 창에서 기존 main.py 실행하기

로그·질문 입력창을 보면서 기존 `/ai`, `/tts`, `test fire` 명령까지 쓰려면 이 방식을 사용합니다. Raspberry Pi 데스크톱 터미널의 프로젝트 폴더에서 실행하세요.

```bash
source .venv-py311/bin/activate
python tools/install_terminal_autostart.py --start
```

등록돼 있던 `edge-saver.service`는 중지·해제하여 중복 실행을 막고, `~/.config/autostart/edge-saver-terminal.desktop`을 만듭니다. `--start`는 현재 데스크톱에도 LXTerminal을 열어 기존 가상환경 Python으로 `main.py`를 실행합니다. `--service`나 오디오 사전 대기 도구를 사용하지 않으며 기존 데스크톱 오디오 환경을 그대로 따릅니다. 수동으로 이미 실행한 앱은 먼저 `q`로 종료하세요.

이후 **데스크톱 로그인 때** 터미널이 자동으로 열립니다. 전원을 켠 후 사용자 입력 없이 시작하려면 Pi의 부팅 대상을 데스크톱으로 설정하고 데스크톱 자동 로그인을 켜야 합니다. `sudo raspi-config` 또는 Raspberry Pi 설정의 Boot/Desktop Auto Login 항목을 사용하며, 메뉴 이름은 설치 버전에 따라 다릅니다. 이 설치 도구가 OS의 자동 로그인 설정을 임의로 바꾸지는 않습니다. [Raspberry Pi 공식 설정 안내](https://www.raspberrypi.com/documentation/computers/configuration.html)

`q`나 창 닫기로 종료하면 다음 로그인 전까지 자동 재시작하지 않습니다. 다시 열려면 프로젝트 가상환경에서 `python tools/run_terminal.py`를 실행하세요. 등록 해제는 `~/.config/autostart/edge-saver-terminal.desktop` 파일을 제거하거나 `Hidden=true`로 바꾸면 됩니다. 기존 systemd 사용자 서비스는 이 방식으로 전환한 뒤 꺼진 상태를 유지합니다.

원격 데스크톱이 별도 세션을 만들면 물리 화면의 터미널이 그 원격 화면에 그대로 나타나지는 않을 수 있습니다. 같은 프로젝트의 터미널 자동 실행은 잠금으로 한 번만 실행하며, 이미 다른 세션에 실행 중이면 중복 실행하지 않습니다. 원격 화면에서 새로 실행하려면 기존 세션의 앱을 먼저 종료하세요. 잠금은 이 도구로 실행한 터미널 간에 적용되므로 별도의 수동 `python main.py`는 중복 실행하지 않습니다.

아래의 systemd 방식으로 되돌리려면 터미널 앱을 `q`로 종료하고 데스크톱 자동 실행 파일을 먼저 해제한 다음 `python tools/install_autostart.py --start`로 재등록합니다. 두 방식을 동시에 활성화하지 않습니다.

## 화면 없는 백그라운드 서비스 방식

`main.py --service`는 터미널 입력 없이 카메라·센서 감시, HTTP 경보 수신, 비상 음성 안내와 반복 방송을 실행합니다. 질문 입력·`/ai`·`/tts` 명령과 음성 질문을 항상 듣는 기능은 이 모드에 없습니다. 설정은 프로젝트의 `.env`를 사용합니다. 기존 `python main.py`와 `python main_test.py` 수동 실행도 유지합니다.

설치 도구는 일반 사용자용 `edge-saver.service`를 등록하고 `linger`를 활성화합니다. 로그인·원격 데스크톱 연결 없이 사용자 서비스가 부팅 때 시작되게 하는 방식입니다. [systemd loginctl 설명](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html#enable-linger%20%5BUSER%E2%80%A6%5D)

현재 구현은 Windows에서 서비스 모드·종료·오디오 선택 로직을 테스트하고, WSL Ubuntu의 실제 systemd 255 검사기에서 서비스 구문을 확인했습니다. 이전 WorkingDirectory 따옴표 오류의 재현과 수정 후 검사 통과를 확인했으며 설치 시에도 대상 Pi에서 검사합니다. 실제 Pi의 재부팅, 카메라·센서·스피커까지 포함한 검증은 아래 절차로 진행해야 합니다.

## 1. 기존 환경 확인

먼저 코드 업데이트 또는 파일 복사를 마치고, **실제 프로젝트 폴더**로 이동합니다. 아래 경로는 기존 시험 폴더 예시입니다. `.env`와 Python 3.11 가상환경, 모델·인덱스는 기존 것을 사용하며 설치 도구가 수정하지 않습니다.

```bash
cd ~/Desktop/-RAG-AI--feature-rpi-vision-optimization
source .venv-py311/bin/activate
python --version
```

실행 중인 `main.py`·`main_test.py`는 `q`로 종료합니다. 같은 카메라·오디오 장치를 쓰는 앱을 중복 실행하지 않습니다. 재난 시뮬레이션 여부는 기존 `SENSOR_MODE` 설정을 그대로 따르므로 실제 배치 전 센서 담당자의 실제 센서 설정을 확인하세요.

## 2. 자동 실행 등록

Pi에서 **일반 사용자로** 실행합니다. Python 명령 앞에 `sudo`를 붙이지 않습니다.

```bash
python tools/install_autostart.py --start
```

설치 도구는 다음을 수행합니다. 원격 데스크톱에서 실행하더라도 `/run/user/사용자UID/bus`를 사용해 부팅용 사용자 서비스 관리자에 연결합니다. 별도 원격 세션의 D-Bus 주소를 그대로 사용하지 않으며, 관리자가 없으면 linger 활성화 후 `sudo systemctl start user@사용자UID.service`로 시작합니다.

1. 프로젝트의 `.venv-py311/bin/python` 또는 `.venv/bin/python`을 찾아 Python 3.11 가상환경인지 확인합니다. 다른 경로는 `--python /절대경로/bin/python`으로 지정합니다. 가상환경의 Python 심볼릭 링크를 시스템 Python 경로로 바꾸지 않습니다.
2. 현재 사용자의 systemd 연결과 `audio`, `video`, `render` 그룹을 확인합니다. 부족하면 필요한 `sudo usermod -aG ... 사용자명` 명령을 표시하고 중단합니다. 그룹 변경 후 재부팅하고 설치 명령을 다시 실행합니다.
3. 로그인 없이 부팅 때 시작하도록 필요한 경우 `sudo loginctl enable-linger 사용자명`을 실행합니다. 이 단계에서 비밀번호를 물을 수 있습니다.
4. `~/.config/systemd/user/edge-saver.service`를 기록하고 활성화합니다. 변경된 기존 파일은 `.service.bak`으로 보관합니다. `--start`가 있으면 현재 서비스도 시작/재시작합니다.

서비스 파일은 기록 전에 `systemd-analyze --user verify`로 검사합니다. `WorkingDirectory`는 명령줄 인자와 달리 경로 전체를 따옴표로 감싸지 않습니다. 이전 설치에서 `bad unit file setting`으로 실패했다면 최신 설치 도구를 다시 실행해 파일을 교체합니다. 성공 시 기존 실패 상태도 초기화합니다.

서비스 파일에 API 키를 복사하지 않으며 프로그램은 기존 프로젝트의 `.env`를 직접 읽습니다. **업데이트만으로 각 Pi에 서비스가 등록되지는 않으므로 이 설치는 Pi마다 한 번 필요합니다.**

미리 내용만 확인하려면 다음 명령을 사용합니다.

```bash
python tools/install_autostart.py --dry-run
```

## 3. 부팅 시 로컬 오디오

기본 설정은 시험 환경인 Raspberry Pi OS의 PipeWire/PulseAudio 호환 출력을 사용합니다. `pipewire`, `pipewire-pulse`, `wireplumber` 사용자 서비스를 요청하고, `pactl`로 출력을 잠시 확인합니다. 오디오가 준비되지 않았거나 `pactl`이 없어도 경고를 남기고 `main.py --service`의 감시를 시작합니다. 오디오 대기 때문에 45초마다 종료·재시작하지 않습니다. 앱 자체가 오류로 종료되면 systemd가 10초 뒤 재시도하며, 관리자가 `systemctl stop`한 경우에는 다시 시작하지 않습니다. [systemd 서비스 재시작 정책](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#Restart=)

기존 수동 실행처럼 오디오 서버의 기본 출력을 사용하며 `xrdp-sink`도 허용합니다. 정상 기본 출력은 `PULSE_SINK`로 고정하지 않습니다. 기본 출력이 없거나 무음 출력(`auto_null`)이면 사용 가능한 다른 출력을 선택하며, 다른 출력도 없어도 감시는 시작합니다. `--pulse-sink`로 명시한 장치만 고정하고 시스템 전체 기본 장치는 바꾸지 않습니다. 여러 스피커가 연결돼 있으면 사용할 장치를 명시할 수 있습니다.

```bash
pactl list short sinks
python tools/install_autostart.py --pulse-sink alsa_output.실제_장치_이름 --start
```

`pactl`은 출력 점검용 도구이며 없으면 점검만 생략합니다. 장치 목록 확인에는 `pulseaudio-utils`를 사용할 수 있습니다. 원격 데스크톱의 PC 스피커와 현장 Pi의 스피커는 다른 출력이며, 원격 연결이 없는 부팅 상황에서 현장에 소리를 내려면 실제 스피커를 연결해야 합니다. Bluetooth는 부팅 시 재연결·프로필 설정도 별도로 확인합니다. 감시 시작과 실제 음성 재생 성공은 구분하여 확인하세요.

PipeWire가 없는 ALSA 전용 환경은 먼저 해당 사용자의 ALSA 기본 출력과 장치 접근 권한을 검증한 뒤 설치합니다.

```bash
python tools/install_autostart.py --audio alsa --start
```

ALSA 모드도 접근 가능한 재생 장치를 잠시 확인한 뒤 감시를 시작합니다. 장치 존재 확인만으로 배선·볼륨·기본 출력 설정까지 검증되는 것은 아닙니다.

## 4. 실행·부팅 검증

```bash
systemctl --user is-enabled edge-saver.service
loginctl show-user "$USER" -p Linger
systemctl --user status edge-saver.service --no-pager
journalctl --user -u edge-saver.service -f
```

위 명령이 `No journal files were found`라고 나오면 사용자 저널의 영구 저장 설정을 바꾸지 않고 시스템 저널에서 조회할 수 있습니다.

```bash
sudo journalctl _SYSTEMD_USER_UNIT=edge-saver.service _UID="$(id -u)" -b -f
```

`enabled`, `Linger=yes`를 확인합니다. `active (running)`은 프로세스가 시작됐다는 뜻이며 모델·장치 준비 완료를 보장하지 않습니다. 로그의 `[서비스] 감지·경보·구역 안내 준비 완료`까지 확인하세요. 전원을 켠 순간부터 즉시 준비되는 것은 아니며 모델·인덱스 로딩 시간이 필요합니다.

이후 Pi를 재부팅하고 **원격 데스크톱 로그인 없이** 카메라·센서·현장 스피커가 동작하는지 확인합니다. 점검용 SSH 연결 후 아래 명령으로 이번 부팅의 로그를 볼 수 있습니다.

```bash
journalctl --user -u edge-saver.service -b --no-pager
```

Gemini는 인터넷과 유효한 API 키가 필요합니다. Ollama 로컬 전환을 사용한다면 모델 준비와 Ollama 서버의 부팅 자동 실행도 별도로 확인합니다.

```bash
systemctl status ollama --no-pager
# Ollama의 시스템 서비스가 설치되어 있고 부팅 시작이 필요한 경우
sudo systemctl enable --now ollama
```

인터넷을 기다리느라 카메라 감시를 시작하지 못하게 하는 별도 네트워크 의존성은 추가하지 않았습니다. 다만 처음 모델을 내려받는 환경은 오프라인으로 준비될 수 없으므로 사전 다운로드가 필요합니다. 캐시 준비를 확인한 완전 오프라인 운영에서는 `.env`의 `HF_HUB_OFFLINE=1` 같은 기존 모델 캐시 설정을 별도로 검토할 수 있습니다.

## 5. 수동 실행·업데이트·해제

원격 데스크톱 터미널에서 `systemctl --user`가 `Failed to get environment` 또는 `org.freedesktop.systemd1` 오류를 내면 다음 연결 변수를 해당 터미널에 먼저 설정합니다. 설치 도구는 이 경로를 자체적으로 사용하지만 부모 터미널 환경까지 변경하지 않습니다. 사용자 버스가 없어 계속 실패하면 `dbus-user-session` 패키지와 `systemctl status user@$(id -u).service`를 확인합니다.

```bash
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
```

수동 질문·데모를 확인하려면 자동 서비스를 먼저 중지합니다.

```bash
systemctl --user stop edge-saver.service
source .venv-py311/bin/activate
python main.py
```

수동 앱을 `q`로 종료한 뒤 자동 서비스를 다시 실행합니다.

```bash
systemctl --user start edge-saver.service
```

코드나 `.env` 업데이트 시에는 `stop` → 업데이트 → `start` 순서로 진행합니다. 경로·가상환경·오디오 방식 변경이나 설치 도구 업데이트가 있으면 설치 명령을 다시 실행합니다. 설치 후 프로젝트 폴더를 옮기면 기존 서비스가 예전 경로를 가리킵니다.

```bash
systemctl --user disable --now edge-saver.service
```

위 명령으로 자동 실행을 해제합니다. `linger`는 다른 사용자 서비스도 사용할 수 있으므로 자동으로 해제하지 않습니다. 다른 서비스에도 필요 없다고 확인한 경우에만 `sudo loginctl disable-linger "$USER"`로 별도 해제합니다.
