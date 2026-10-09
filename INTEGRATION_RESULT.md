# 통합 결과 — 2026-10-09

현재 비전 코드를 기반으로 feature/RAG `ec99c872`의 검색·provider·음성 기능을 통합했습니다. Git checkout이 없는 파일 폴더에서 작업했으며 커밋·푸시는 수행하지 않았습니다.

## 반영한 기능

- 경량 YOLO 선택, ndarray 직접 전달, Optical Flow와 기존 비전 가중치 보존.
- 비전 파일 4개와 sensors/fusion.py는 사용자 요청으로 통합 전 백업과 바이트 단위 동일하게 복원.
- vision_bridge.py 연결부에서 동일 프레임 객체의 반복 추론을 방지. 시간은 카메라 촬영 시각이 아니라 연결부 최초 관찰 시각이며, 원본의 camera_offline 표시를 사용.
- 원본 불꽃 판정·모션 카운트 감소·센서 퓨전의 조기 연기 분기 유지. 연결부는 비전 판정 값을 재해석하지 않음.
- feature/RAG의 FAISS·BM25·검색 의도 처리·선택적 reranker·문서 변경 감지.
- 매뉴얼 컨텍스트·구역별 평면도·Gemini/Ollama/고정 안내 전환.
- PPASO TTS, 한국어 문장 전처리, 취소된 합성 결과 재생 방지.
- 시스템 TTS를 별도 프로세스로 실행해 일반 발화를 중단할 수 있게 처리.
- Whisper STT 캐시 우선 로딩, 첫 음성 요청에서만 초기화. 기본 CPU 모델은 small.
- 감시와 RAG 생성을 분리하고, 첫 비상 안내는 생성 작업을 기다리지 않음.
- 정상 복귀 후 과거 경보 결과, 비상 중 일반 질문 결과를 폐기.
- 데모/실센서 모드 분리와 고정 구역 설정. 실센서 실패는 가상 정상값으로 대체하지 않음.
- 사이렌 종료 시 공유 TTS mixer를 종료하지 않음.
- 현재 실행 환경에 프로젝트 가상환경·PPASO 자원·121개 청크 인덱스 준비.
- NumPy 1.x 호환 범위, ONNX 관련 의존성 명시. 런타임 캐시는 프로젝트 scratch 사용.

## 비전 복원 — 2026-10-09

비전 담당 영역의 임의 변경을 피하기 위해 vision/cctv_service.py, vision/fire_detector.py, vision/smoke_motion.py, vision/test_unit_verification.py 및 sensors/fusion.py를 원본 백업으로 복원했습니다. 원본 cctv_service의 Windows sys 누락은 vision_bridge.py에서 모듈 로딩 시 보완합니다. 원본에 없던 reset_motion 호출은 제거했습니다. 변경했던 판정에 의존하는 테스트 5개는 현재 테스트에서 제거하고 scratch/vision_changes_before_revert_20261009에 보관했습니다. RAG·TTS·STT와 비상 작업 우선순위는 유지합니다. 센서 읽기 모듈의 hardware 실패 처리 및 main.py의 데모/실센서 분리는 이번 복원 대상에 포함하지 않습니다.

복원 후 검증: 원본 백업과 5개 파일의 바이트 동일성 확인, unittest 46개 통과, 수정된 Python 소스 구문 검사 통과. 실제 YOLO·RAG·PPASO를 사용하는 실행부 smoke 검사도 성공했습니다(합성 카메라·무음 출력, 의도적으로 설정한 Ollama 2초 제한 후 고정 안내 전환). 실제 카메라·스피커는 검증하지 않았습니다. 아래 검증 표는 복원 전 통합 버전의 기록입니다.

## 수행한 검증

| 검증 | 결과 | 실제 검증 범위 |
|---|---|---|
| unittest 회귀 테스트 | 51개 통과 | 공급자 전환 mock, 비전 판정 경계, 감시·경보·질문 우선순위, 지연 결과 폐기, TTS 취소 |
| 기존 비전 검증 스크립트 | 통과 | 모션 5종·퓨전 5종, 실제 ONNX 검정 이미지 추론, VLM 시뮬레이션 |
| 검색 품질 확인 | 8/8 | 실제 임베딩과 새 인덱스에서 상위 2개 근거 확인 |
| PPASO 벤치마크 | WAV 3개 생성 성공 | 실제 한국어 합성. 스피커 재생은 제외 |
| WAV→Whisper small | 성공 | 합성 대피 문장을 한국어로 정확히 인식. 마이크 제외 |
| 실행부 smoke 검사 | 성공 | 실제 모델·인덱스·TTS, 합성 카메라, SDL 무음 재생, 로컬 응답 지연 시 고정 안내 |
| 실제 로컬 RAG 답변 | 성공 | 공장 화재 질문→실제 검색→Ollama qwen2.5:0.5b→PPASO WAV |

Windows PC에서 측정한 참고 수치:

- PPASO 샘플 3개 합성: 약 0.77 / 1.23 / 1.89초.
- Whisper small: 모델 로딩 약 9.13초, 4.76초 길이 합성 음성 인식 약 6.56초.
- 실행부 smoke: 초기화 약 3.95초. import 시간은 이 값에 포함되지 않음.
- 실제 공장 질문: 검색 약 0.11초, Ollama 답변 약 10.79초, PPASO 초기화 포함 합성 약 7.64초.

각 측정은 단일/소수 샘플이며 전체 경보 반응 시간 또는 Pi 성능을 의미하지 않습니다. Gemini 실제 호출, 답변의 의미 정확도, 실장치 내구성은 이 검사로 검증하지 않았습니다.

## 확인할 사항

1. 실제 카메라에서 정지 사진·손떨림·연기·불꽃 회귀 확인.
2. 마이크 입력 및 실제 스피커의 PPASO·사이렌 동시 출력 확인.
3. Pi에서 설치, MeCab·ALSA·GPIO 드라이버, CPU/메모리·감시 간격 확인.
4. `.env`의 ZONE_ID를 현장에 맞게 설정하고 실제 평면도 검토.
5. SENSOR_MODE=hardware 활성화 전 실제 센서 연결 확인.
6. 클라우드를 사용한다면 API 키·모델 접근 및 GEMINI_SEND_LAYOUT 설정 확인.

GUI와 외부 관제 전송은 이번 통합에 포함하지 않았습니다. 관제 알림은 현재 콘솔 출력입니다. PPASO 합성 자체는 계산 중 강제 취소하지 않으므로, 이전 합성 계산이 끝난 뒤 비상 발화를 시작할 수 있습니다. 취소된 결과는 재생하지 않습니다.

## 결과 파일

추가 반영: feature/RAG의 main_test.py를 평시 문답 테스트 실행부로 가져왔습니다. vision_bridge 사용, 기존 ndarray 비전 입력 유지, config 캐시 설정 선행, 오래된 인덱스 갱신, TTS 로그 노출과 종료 시 close 호출을 적용했습니다. 비전 소스는 변경하지 않았습니다. 원격 테스트 모드의 센서 시뮬레이션·비상 개입 비활성화·질문별 시간 및 출처 출력은 유지합니다. 시작 로그에서 reranker 실제 ON/OFF 설정도 표시합니다.

- `scratch/rag_quality_after.json`: 검색 확인.
- `scratch/integration_tts_benchmark/`: WAV·시간·메모리 측정.
- `scratch/voice_roundtrip.json`: 오프라인 STT 결과.
- `scratch/integration_smoke.json`: 실행부 smoke 결과.
- `scratch/local_guidance.json`, `scratch/local_guidance.wav`: 실제 로컬 답변과 합성 음성.
- `scratch/integration_backup_20261009/`: 기존 코드·인덱스 복구 자료.

실행과 설치 방법은 README.md를 참고하세요.

main_test.py UI 후속 수정: 입력 프롬프트 0.5초 갱신, 단일 문답 작업 스레드로 검색·답변·TTS 대기 분리, 답변 중 다음 질문 입력, 새 질문/마이크 입력/종료 시 과거 결과 발화 방지를 적용했습니다. 감시 메서드는 변경 전과 AST가 동일하며 비전 코드도 변경하지 않았습니다. 전체 회귀 49개 통과 후 추가한 프롬프트 재진입·마이크 전환 검증을 포함해 최종 문답 테스트 5개가 통과했습니다. 실제 터미널 화면 및 마이크·스피커는 별도 실사용 확인이 필요합니다. 변경 전 파일은 scratch/main_test_before_async_ui_20261009.py에 보관했습니다.

설치 파일·Pi 가이드의 누락을 점검하고 보완했습니다. .env.example 및 Pi 이전/MeCab 안내 복원, 공통 직접 의존성 명시, requirements UTF-8 처리, 현재 통합 실행과 다른 옛 설치 절차 수정이 포함됩니다. 실제 .env와 비전·센서 구현은 변경하지 않았습니다.
