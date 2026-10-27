# Raspberry Pi 전원 켤 때 자동 실행

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

기본 설정은 시험 환경인 Raspberry Pi OS의 PipeWire/PulseAudio 호환 출력을 사용합니다. `pipewire`, `pipewire-pulse`, `wireplumber` 사용자 서비스를 요청하고, `pactl`로 최대 45초간 출력 장치를 확인합니다. 준비되지 않으면 실패로 종료하고 systemd가 10초 뒤 재시도합니다. 앱이 오류로 종료돼도 자동 재시작하며, 관리자가 `systemctl stop`한 경우에는 다시 시작하지 않습니다. [systemd 서비스 재시작 정책](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#Restart=)

기본 출력이 로컬 장치면 유지하고, 아니면 `alsa_output.*` 또는 `bluez_output.*` 중 로컬 장치를 선택합니다. `xrdp-sink`나 `auto_null`만 있으면 실행을 보류합니다. 프로그램 프로세스의 `PULSE_SINK`만 설정하며 시스템 전체 기본 장치를 바꾸지 않습니다. 여러 스피커가 연결돼 있으면 사용할 장치를 명시하는 것이 정확합니다.

```bash
pactl list short sinks
python tools/install_autostart.py --pulse-sink alsa_output.실제_장치_이름 --start
```

`pactl`이 없으면 기본 모드에 `pulseaudio-utils`가 필요합니다. 물리 스피커·HDMI·USB 사운드카드는 미리 연결하고 실제 재생으로 확인하세요. 원격 데스크톱의 PC 스피커와 현장 Pi의 스피커는 다른 출력입니다. Bluetooth는 부팅 시 재연결·프로필 설정도 별도로 확인해야 합니다.

PipeWire가 없는 ALSA 전용 환경은 먼저 해당 사용자의 ALSA 기본 출력과 장치 접근 권한을 검증한 뒤 설치합니다.

```bash
python tools/install_autostart.py --audio alsa --start
```

ALSA 모드는 접근 가능한 재생 장치가 생길 때까지 기다립니다. 장치 존재 확인만으로 배선·볼륨·기본 출력 설정까지 검증되는 것은 아닙니다.

## 4. 실행·부팅 검증

```bash
systemctl --user is-enabled edge-saver.service
loginctl show-user "$USER" -p Linger
systemctl --user status edge-saver.service --no-pager
journalctl --user -u edge-saver.service -f
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
