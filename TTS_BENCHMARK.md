# TTS 단독 벤치마크

프로젝트 루트에서 실행합니다. GUI·RAG·센서 서비스 없이 pyttsx3, PPASO, MeloTTS를 순차 실행하며 스피커 재생 대신 WAV 파일을 생성합니다. 각 엔진은 별도 Python 프로세스로 측정합니다.

```bash
python tools/benchmark_tts.py --repeats 5
```

짧은 확인 또는 특정 엔진만 측정:

```bash
python tools/benchmark_tts.py --engines ppaso --repeats 1
python tools/benchmark_tts.py --engines pyttsx3 ppaso melo --repeats 10 --timeout 1200
python tools/benchmark_tts.py --text-file benchmark_sentences.txt
```

`--text-file`은 UTF-8 파일이며 빈 줄을 제외한 각 줄을 하나의 시험 문장으로 사용합니다. 기본값은 한국어 대피 안내문 3개입니다. PPASO 모델 경로는 `--ppaso-model-dir`로 지정할 수 있습니다.

## 실행 전 준비

- 측정 도구는 현재 활성화한 Python 환경을 자식 프로세스에도 사용합니다. 각 실행 환경에 `psutil`, `soundfile`이 필요합니다. 의존성 충돌이 있으면 엔진별 가상환경으로 나누어 같은 문장·반복 횟수로 각각 측정합니다. 결과에 Python·패키지 버전 차이를 함께 표시하세요.
- PPASO는 `models/ppaso`의 런타임·ONNX 가중치와 ONNX Runtime이 필요합니다.
- MeloTTS는 Melo 패키지와 한국어 모델·BERT 캐시, 형태소 분석기 등 의존성을 미리 준비합니다. NLTK의 `cmudict`, `averaged_perceptron_tagger` 데이터도 필요합니다. Hugging Face 모델 다운로드는 측정 중 차단합니다. 버전에 따라 추가 NLTK 데이터가 필요하면 먼저 준비해야 합니다.
- pyttsx3는 Windows에서 한국어 SAPI5 음성, Linux에서 한국어를 지원하는 eSpeak 음성이 필요합니다. 한국어 음성을 찾지 못하면 실패로 기록합니다.
- Raspberry Pi에서는 64비트 OS/엔진 지원 여부를 먼저 확인합니다. 같은 전원·냉각·OS·모델 버전으로 비교하고, 다른 서비스를 종료한 상태에서 측정합니다. 이후 실제 앱을 함께 실행한 상태도 별도로 측정하면 동시 실행 부담을 확인할 수 있습니다.

### 기본 앱과 Melo 환경을 나누는 경우

기본 앱은 `requirements_rpi.txt`를 설치하고 PPASO를 준비합니다. MeloTTS는 이 목록에 포함하지 않습니다. 별도 Python 3.11 가상환경 `.venv-melo`에 [공식 MeloTTS 설치 안내](https://github.com/myshell-ai/MeloTTS/blob/main/docs/install.md)에 따라 소스·의존성을 설치합니다. 프로젝트 루트에서 활성화한 뒤 측정합니다.

```bash
source .venv/bin/activate
python tools/benchmark_tts.py --engines pyttsx3 ppaso --repeats 5 --timeout 1200
deactivate
source .venv-melo/bin/activate
python -m pip install psutil soundfile
python -c "from melo.api import TTS; print('Melo import ok')"
python tools/benchmark_tts.py --engines melo --repeats 5 --timeout 1200
```

`.venv` 부분은 실제 기본 앱 가상환경 경로로 바꿉니다. Melo import 성공과 한국어 모델 합성 성공은 별개입니다. 측정 전 한국어 모델·BERT 캐시를 준비하세요. `pkg_resources` 오류가 발생하는 구형 librosa 조합은 `setuptools<81`가 필요할 수 있습니다. `unidic/dicdir/mecabrc` 누락은 해당 Melo 환경에서 `python -m unidic download`로 일본어 사전을 준비합니다. NLTK 자료도 그 환경에서 준비합니다.

```bash
python -m nltk.downloader cmudict averaged_perceptron_tagger averaged_perceptron_tagger_eng
```

모든 엔진을 하나의 환경에서 실행할 수 있을 때만 상단의 전체 엔진 명령을 사용하세요. 기본 앱 설치와 MeCab 확인은 [Pi 이전 가이드](raspberry_pi_migration.md)를 참조하세요.

## 결과와 해석

기본 저장 위치는 `scratch/tts_benchmark/날짜_시간/`입니다. `--output`으로 변경할 수 있습니다. 기존 엔진 결과가 있는 폴더는 재사용하지 않습니다.

| 결과 | 설명 |
|---|---|
| `comparison.csv` | 문장별 중앙값, 성공 횟수, 초기화 시간, 첫 합성 시간, 최대 RSS(MiB) |
| `comparison.json` | OS·Python·RAM·CPU 정보, 엔진 버전, 원시 측정 결과 |
| `엔진/result.json` | 개별 결과, 오류, Pi 온도·ARM 클럭·스로틀링 전후 상태 |
| `엔진/worker.log` | 엔진 로그와 오류 원인 |
| `엔진/*.wav` | 첫 합성 및 반복 결과. 발음·자연스러움은 직접 청취해 평가 |

- **초기화 시간**: 엔진 관련 모듈 import와 모델 초기화. 프로세스 시작 비용 및 공통 측정 라이브러리 import는 제외합니다. Melo의 지연 로딩은 첫 합성 시간에 포함될 수 있습니다.
- **첫 합성 시간**: 최초 문장 1회. 반복 중앙값에는 포함하지 않습니다. 초기화+첫 합성으로 처음 WAV가 준비되는 비용을 볼 수 있습니다. OS 파일 캐시를 비우지는 않으므로 완전한 콜드 부팅 측정은 아닙니다.
- **합성 시간**: 입력 문장부터 WAV 저장 완료까지. 같은 문장끼리 비교하며 서로 다른 문장을 합쳐 중앙값을 계산하지 않습니다.
- **RTF**: 합성 시간 ÷ 생성 음성 길이. 1 미만이면 음성 재생 길이보다 빠르게 생성합니다. 말하기 속도가 다를 수 있으므로 합성 시간과 음성 길이도 함께 제시합니다.
- **최대 RSS**: 측정 자식 프로세스 전체의 메모리이며 Python·모델·라이브러리를 포함합니다. Linux는 `ru_maxrss`, Windows는 10ms 간격 RSS 표본의 최대값입니다. Windows는 짧은 피크를 놓칠 수 있습니다. 시스템 서비스·별도 프로세스·전체 RAM 사용량은 제외합니다.
- **CPU 시간**: 해당 프로세스가 사용한 CPU 시간이며 여러 스레드의 합이므로 실제 경과 시간보다 클 수 있습니다. CPU 사용률(%)과는 다릅니다. 모든 엔진은 CPU와 기본 스레드 설정으로 실행합니다.
- Pi의 `vcgencmd`가 있으면 전후 상태를 기록하며 없으면 null로 남깁니다. `get_throttled`가 0이 아닌 경우 과열·전원 제한 이력을 확인하고 재측정합니다.
- 오류나 제한 시간 초과는 정상 성능 결과와 구분합니다. 프로그램은 다른 엔진을 계속 측정한 뒤 하나라도 실패하면 종료 코드 1을 반환합니다. 실패한 엔진의 부분 결과를 정상 벤치마크로 사용하지 마십시오.

### pyttsx3 비교 시 주의

Windows는 반복 `save_to_file/runAndWait`에서 멈추는 pyttsx3 버전을 고려해 내부 SAPI5 드라이버의 동기 파일 합성을 사용합니다. 이는 버전에 종속되는 경로이며 결과에 `file_api`로 기록됩니다. Linux는 공개 `save_to_file/runAndWait`를 사용합니다. 따라서 Windows 결과와 Raspberry Pi 결과를 같은 백엔드 성능으로 취급하면 안 됩니다.

파일 합성 수치는 실제 앱의 큐·엔진 재생성·스피커 출력 지연을 포함하지 않습니다. 이 도구로는 실제 첫 발화 지연이나 음성 품질 점수를 주장할 수 없습니다. Windows의 기존 Melo 래퍼는 MeCab 대체 처리를 사용하므로 발음 평가도 별도로 해야 합니다.
