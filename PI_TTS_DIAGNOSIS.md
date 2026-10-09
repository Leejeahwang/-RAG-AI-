# feature/RAG 라즈베리파이 TTS 진단

2026-10-09 원격 fetch로 확인한 feature/RAG 커밋: ec99c872e9f2074a569d81db1dadd47f16ccc91c.
라즈베리파이에 직접 접속하지 않았으므로 실제 장애 원인은 아직 확정하지 않았습니다.
이 문서는 통합 작업 폴더의 TTS 구현과 원격 feature/RAG의 구현을 구분합니다.

## 코드에서 확인한 사항

1. feature/RAG의 config.py 기본값은 TTS_ENGINE="PPASO"입니다. 따라서 터미널 espeak 성공은 프로젝트의 PPASO 합성 및 pygame 재생 성공을 뜻하지 않습니다.
2. feature/RAG의 voice/tts.py는 PPASO 초기화 실패에도 엔진 준비 완료를 출력합니다. speak_to_file이 실패하면 로그만 남기고 큐 작업을 끝냅니다. espeak 또는 PYTTSX3 폴백은 없습니다.
3. feature/RAG의 PYTTSX3 분기는 lang='ko'를 받아도 voice 속성을 설정하지 않습니다. 한국어 지원이 확인된 espeak -v ko와 다른 경로입니다. 이것만으로 완전 무음의 원인이 확정되지는 않습니다.
4. feature/RAG의 voice/tts_worker.py에는 espeak-ng 직접 호출이 있지만 voice/tts.py에서 이 파일을 실행하지 않습니다. 이 파일만 변경해도 실제 TTS 경로에는 반영되지 않습니다.
5. PPASO 모델 디렉토리는 현재 작업 디렉토리를 기준으로 해석합니다. 다른 디렉토리에서 실행하면 모델을 찾지 못할 수 있습니다. 초기화 실패 로그에 실제 이유가 출력됩니다.
6. pygame mixer 초기화·재생 오류도 로그로 출력하지만 준비 완료 문구는 나옵니다. 출력 장치 또는 실행 세션이 다르면 espeak와 결과가 다를 가능성이 있으므로 WAV 재생을 분리해서 확인해야 합니다.

현재 통합 작업 폴더에는 PPASO 초기화 실패 시 PYTTSX3 폴백이 있습니다. 다만 여기의 Linux 시스템 음성은 pyttsx3를 사용하며, 원격 feature/RAG의 espeak-ng 워커와 동일하지 않습니다.
이번 조사에서 기존 비전·센서·음성 구현은 변경하지 않았습니다. 진단 파일만 추가했습니다.

## 조원 PC에서 실행

tools/diagnose_pi_tts.py를 조원의 feature/RAG 체크아웃 tools 폴더에 복사합니다.
프로젝트를 실행하는 동일한 사용자·터미널·가상환경을 사용하고, 프로젝트 루트에서 아래 명령을 각각 실행합니다.
python은 실제 프로젝트 실행에 사용하는 Python 명령으로 바꿉니다. sudo로 실행 환경을 바꾸지 않습니다.

```bash
git rev-parse HEAD
python tools/diagnose_pi_tts.py --stage inspect
python tools/diagnose_pi_tts.py --stage synth
aplay scratch/pi_tts_probe.wav
python tools/diagnose_pi_tts.py --stage play
python tools/diagnose_pi_tts.py --stage project
```

inspect와 synth는 음성을 재생하지 않습니다. 나머지 재생 단계는 소리가 들리는지 직접 확인합니다.
프로젝트가 돌아가는 동안의 장치 점유를 피하려면 먼저 프로젝트를 종료하고 테스트합니다.
첫 합성이 느려 명령이 오래 걸리는 경우 synth의 결과와 project의 120초 제한을 구분합니다.

| 결과 | 다음으로 볼 위치 |
|---|---|
| synth에서 초기화 실패 | PPASO 모델 경로, ppaso_tts·ONNXRuntime·MeCab·soundfile 오류 |
| synth 성공, aplay 실패/무음 | WAV 파일 및 ALSA 출력 장치·음량·실행 세션 |
| aplay는 들리고 play는 실패/무음 | pygame/SDL 출력 경로·mixer 초기화 오류 |
| play는 들리고 project는 실패/무음 | 설정된 TTS 엔진, 큐·합성 로그, 선택한 음성 경로 |
| project 단독은 들리고 main.py만 무음 | 실제 speak 호출 여부, 경보 복구/stop 호출, 동시 재생·장치 점유 |

project의 QUEUE FINISHED는 청각적 성공 판정이 아닙니다. 원격 feature/RAG는 합성 실패에도 큐를 비우므로 위쪽 오류 로그와 실제 소리를 함께 확인해야 합니다.

추가로 필요한 정보: 사용한 커밋, 성공한 정확한 espeak 명령, TTS 시작 로그, 각 단계 결과, HDMI/USB/블루투스 등 출력 장치, 로컬 터미널/SSH/서비스 중 실행 방식.

참고: https://www.pygame.org/docs/ref/mixer.html 및 https://github.com/nateshmbhat/pyttsx3/blob/master/pyttsx3/engine.py.
