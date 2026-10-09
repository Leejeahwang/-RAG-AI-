# 설치·문서 통합 누락 점검 — 2026-10-09

대조 기준: 현재 실행 코드, 원격 feature/RAG ec99c872, 통합 전 백업, 공식 PyTorch·MeCab·Raspberry Pi·pygame 문서.

## 발견 사항과 반영

| 대상 | 발견 사항 | 반영 |
|---|---|---|
| requirements.txt | WAV 검증 도구의 scipy와 직접 사용하는 langchain-core가 명시되지 않음 | 직접 의존성 명시, 기존 NumPy/OpenCV 제약 유지 |
| requirements*.txt | Windows CP949 pip에서 UTF-8 한글 주석을 디코딩하지 못해 설치 명령 실패 | 모든 requirements 파일에 UTF-8 coding 선언 추가 |
| requirements_rpi.txt | 없는 migration 문서 참조, Adafruit_DHT 미설치 이유 불명확 | 상세 가이드 복원, DHT11/Pi 5 드라이버 미검증과 테스트 모드 동작 명시 |
| .env.example | README에서 참조하지만 파일 없음 | 현재 config.py에서 읽는 환경변수 예시 복원; 실제 .env는 변경하지 않음 |
| README.md | Pi 시스템 패키지·MeCab·모델 이동·음성 진단 설명 부족 | 개발 헤더/빌드 도구/ALSA 도구, 상세 가이드 링크, 모델 준비 범위와 선택 의존성 설명 |
| rpi5_setup_guide.md | rpi 브랜치/1.5b/PYTTSX3 안내가 현재와 다름; libfaiss-dev를 Python FAISS 대체로 안내 | 현재 통합 폴더 이전·0.5b·PPASO 기준으로 재작성, 잘못된 설치 안내 제거 |
| rpi5_setup_guide.md | Windows SAPI와 Linux TTS 혼동; libcamerify 완전 호환 및 세 항목 대피 응답 보장 | 실제 엔진/카메라 폴백/첫 고정 안내·후속 안내 동작 설명 |
| raspberry_pi_migration.md | 원격에서 누락된 핵심 Pi/MeCab 이전 문서 | 복원 후 현재 코드에 맞춰 STT 타깃, 센서 실패, GUI 제외, 음성 진단을 갱신 |
| 기술 참고 문서 | 과거 벤치마크·비교 기록은 현재 설치에 불필요 | 사용자 요청으로 루트의 참고 문서 7개 제거하고 현재 가이드의 참조 정리 |
| Chroma 비교 | 선택 벤치마크의 chromadb 설치 목록 없음 | requirements_benchmarks.txt로 기본 앱과 구분 |

streamlit/pandas는 현재 GUI 구현이 예정 상태여서 기본 목록에 다시 넣지 않았습니다. MeloTTS는 별도 비교 환경 안내를 유지합니다. 원본 PDF/OCR는 requirements_documents.txt를 사용합니다. OpenVINO/TFLite 런타임은 기본 ONNX/PT 환경과 구분하며 비전 모델 선택 로직은 변경하지 않았습니다. Adafruit-DHT의 Pi 5 호환성은 확인되지 않아 무조건 설치하는 해결책으로 처리하지 않았습니다.

## 검증

- requirements 파일 전체의 구문 및 -r 참조 파일 확인.
- 현재 Windows Python 3.11 환경에서 requirements.txt 직접 항목 36개가 설치 버전·제약과 일치함을 확인.
- pip install --dry-run --no-index -r requirements.txt 통과. 패키지를 설치하거나 변경하지 않음.
- README, Pi 5 가이드, migration 가이드의 Markdown 로컬 링크 존재 확인.
- 복원한 비전 파일 4개와 sensors/fusion.py가 통합 전 백업과 바이트 단위 동일함을 재확인.

이 검증은 기존 Windows 가상환경 기준입니다. 새 ARM64 환경의 의존성 해결, apt 설치, 전체 모델 설치, 마이크·스피커·GPIO 동작은 Pi에서 별도로 검증해야 합니다. requirements는 완전한 버전 잠금 파일이 아닙니다. 실행 코드 변경이 없어 기존 유닛 테스트를 반복하지 않았습니다.

점검 결과: scratch/install_docs_audit.json. 변경 전 설치 파일과 가이드: scratch/install_docs_before_audit_20261009/.
