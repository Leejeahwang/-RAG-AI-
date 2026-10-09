# 비전 유지 + feature/RAG 통합 계획

실행 결과: 이후 통합을 수행했으며, 완료 범위와 검증 결과는 [INTEGRATION_RESULT.md](INTEGRATION_RESULT.md)를 참고한다.

작성일: 2026-10-09 (Asia/Seoul)

## 목표와 비교 기준

현재 프로젝트의 카메라 수집, 경량 YOLO 모델 선택, 메모리 프레임 전달, Optical Flow 분석, 비전 테스트를 유지한다. `feature/RAG`의 매뉴얼 검색·답변 생성·TTS·STT 기능을 이 실행 경로에 연결한다.

- 원격 저장소: https://github.com/Leejeahwang/-RAG-AI-.git
- 비교 브랜치: `feature/RAG`
- 비교 커밋: `ec99c872e9f2074a569d81db1dadd47f16ccc91c`
- 현재 폴더에는 `.git`이 없어 로컬 브랜치·기반 커밋은 확인할 수 없다. 파일 스냅샷을 비교했다.
- 이번 작업은 계획 작성과 읽기 중심 비교다. 실행 코드 통합, 모델 다운로드, 인덱스 재구축, 원격 푸시는 수행하지 않았다.

## 비교에서 확인한 사항

| 영역 | 현재 프로젝트 | feature/RAG | 통합 방침 |
|---|---|---|---|
| 비전 | 경량 모델 우선, ndarray 전달, 모션 분석 | 다른 감지기, main.py에서 임시 이미지 파일 생성, 감시 루프 3초 대기 | 현재 비전 경로 유지 |
| 센서 퓨전 | 모션·사진·조기 연기 정보를 dict로 수신 | main.py에서 bool 감지값 전달 | 현재 dict 기반 계약 유지 |
| RAG | FAISS + BM25 + 규칙 재정렬 | 한국어 bigram, 검색 의도 처리, 선택적 BGE, 문서 변경 감지 | feature/RAG의 검색 모듈 이식 |
| 답변 생성 | Ollama 토큰 직접 소비 | provider 계층, Gemini→Ollama→고정 비상 안내 | provider 계약으로 연결 |
| 컨텍스트 | main.py 내부 정제 | context.py, layout.py로 분리 | feature/RAG 모듈 사용 |
| TTS | PYTTSX3 기본 | PPASO 기본, Melo 지연 import, 발화 완료 대기·종료 처리 | feature/RAG TTS 사용, 실음성 확인 |
| STT | 기본 비활성화 | Windows 기본 활성화, Pi 기본 비활성화, 캐시 모델 우선 사용 | 코드 이식과 Pi 활성화 검증 분리 |
| 관제 GUI | 미구현 | Streamlit 대시보드 및 작업자 | 1차 통합 이후 별도 단계 |

파일 차이를 줄바꿈 정규화 후 비교하면 `voice/ppaso_wrapper.py`, `melo_wrapper.py`, `piper_helper.py`, `tts_worker.py`, `find_sound.py`, `sweep_apis.py` 등은 동일하다. 실제 음성 변경의 중심은 `voice/tts.py`, `voice/stt.py`, 설정, 모델 준비, 실행부 연결이다.

## 파일별 반영 범위

### 현재 프로젝트를 기준으로 유지

- `vision/fire_detector.py`: 경량 모델 우선순위와 ndarray 입력 유지.
- `vision/smoke_motion.py`: 현재 모션 검증 방식 유지.
- `vision/cctv_service.py`: 현재 카메라 탐색·프레임 전달 방식 유지.
- `vision/models/`, 비전 검증 스크립트: 가중치와 시나리오 보존.
- `sensors/fusion.py`: 모션·조기 연기 정보 수신 기능 유지.
- `data/zone_*_layout.txt`: 현재 현장 자료를 우선 보존하고 원격 자료와 내용 검토.

비전 보존은 현재 오작동까지 고정한다는 의미가 아니다. 아래 필수 수정은 별도 변경으로 관리하고 회귀 검증한다.

### feature/RAG에서 가져오기

- 필수 RAG: `native_retriever.py`, `loader.py`, `chain.py`, `context.py`, `layout.py`, `provider.py`, `search_intent.py`.
- 음성: `voice/tts.py`, `voice/stt.py`; 동일한 래퍼들은 유지하고 필요한 자원만 준비.
- 도구: `tools/rebuild_rag_index.py`, `check_rag_quality.py`, `rag_quality_dataset.py`, RAG·TTS 벤치마크 및 그 의존 파일.
- 테스트: `tests/`의 컨텍스트·구역·provider·검색 의도·TTS 테스트.
- 설치: `requirements*.txt`, `.env.example`, `download_models.py`, 설치 문서의 관련 부분.
- 매뉴얼: `data/chunked_manuals.json`과 근거 문서의 대응 관계 확인 후 반영. 동일 원문이 JSON과 TXT로 중복 수집되지 않는지 점검.
- 선택 사항: `parser.py`, `chunker.py`, 문서 가공 의존성. 기존 TXT/JSON 실행과 분리한다.

### 수동 연결

- `main.py`: 현재 비전 감시 흐름에 feature/RAG의 질의·provider·음성 동작을 연결한다. 원격 main.py 전체 덮어쓰기는 피한다.
- `config.py`: 비전 설정과 RAG·음성 설정을 병합한다. CAMERA_INDEX와 BYPASS_MOTION_FILTER를 유지한다.
- `alerts/alarm.py`: PPASO 재생과 사이렌의 pygame mixer 소유·종료 순서를 검토한다.
- `alerts/notifier.py`: 실제 위험도와 고정 구역을 전달한다. 콘솔 알림을 외부 관제 전송으로 오인하지 않게 한다.
- `faiss_db/`: 기존 인덱스를 백업하고 통합 문서와 새 검색 코드로 재구축한다. BM25 pickle만 교체하거나 두 브랜치 인덱스를 혼합하지 않는다.

## 실행 구조

```text
카메라 수집 → 최신 프레임 → 현재 YOLO·모션 분석
                                    ↓
센서 수집 ─────────────────────── 위험도 계산
                                    ↓
                              비상 이벤트 큐
                                    ↓
                         사이렌 + 고정 첫 안내
                                    ↓
                     RAG 검색 → provider → 추가 TTS 안내

텍스트 / STT → 일반 질문 작업자 → 같은 RAG·provider → TTS
```

감시 루프는 RAG·네트워크·음성 완료를 기다리지 않는다. 일반 질문과 긴급 이벤트의 입구를 분리하되 답변 생성 모듈은 공용으로 사용한다.

### 연결 계약

1. 비전 결과는 `fire_detected`, `is_real_smoke`, `is_static_photo`, `confidence`, `status`, `description`을 유지한다. 불꽃 최종 확정 상태와 후보 분석 상태를 구분한다.
2. 위험 이벤트에는 `event_id`, `zone_id`, `level`, `details`, `timestamp`를 포함한다. 카메라 ID 또는 장치 설정에서 구역을 결정한다.
3. 검색 호출은 `rag_manager.search(question)`으로 시작하고 `build_manual_context(docs)`로 근거를 정제한다.
4. 로컬 컨텍스트에는 명시된 구역의 평면도를 추가한다. 클라우드 컨텍스트는 feature/RAG의 `GEMINI_SEND_LAYOUT` 설정을 따른다.
5. 답변은 `generate_guidance(context, question, emergency=..., cloud_context=...)`로 생성하고 `GuidanceResult.text/provider/fallback_reason`을 소비한다.
6. TTS는 한 개의 관리 경로에서 직렬 실행한다. 긴급 이벤트는 일반 답변의 대기 발화를 제거하고 첫 비상 안내를 우선한다.
7. 늦게 끝난 일반 질문 결과와 정상 복귀 후 도착한 과거 경보 답변은 출력하지 않는다. 요청·이벤트 세대 번호로 결과 유효성을 확인한다.
8. 단일 플래그로 실제 진행 중인 HTTP 요청이 취소된다고 가정하지 않는다. 타임아웃, 결과 폐기, 생성 작업의 동시 실행 제한을 함께 적용한다.

feature/RAG의 `generate_guidance`는 완성된 답변을 반환한다. 현재 main.py의 토큰 단위 반복에 그대로 연결하면 안 된다. 일반 답변은 완성 결과를 발화하고, 긴급 상황은 고정 첫 안내를 먼저 내보낸 뒤 근거 있는 추가 안내를 발화한다.

## 필수 수정과 충돌 지점

| 문제 | 처리 | 완료 조건 |
|---|---|---|
| CCTV의 sys import 누락 | 현재 cctv_service.py 수정 | Windows import 성공 |
| 모션 WARMING_UP/EVALUATING 상태도 화재 확정 | 최종 모션 판정으로 fire_detected 결정, bypass는 명시적 데모 모드 | 후보 프레임은 경보 미발생, 검증 후 확정 |
| 실제 연기에 fire_detected=True를 주어 조기 감지 분기 우회 | 비전·퓨전의 연기 의미 계약 정리 | 실제 감지기 결과로 early detection 통합 테스트 통과 |
| 일반 생성 중 감시 중단·긴급 생성 동기 실행 | 감시에서 생성 작업 분리 | 느린 답변 중에도 감시 지속 |
| 무작위 zone_id | 장치별 고정 구역 매핑 | A구역 이벤트가 B/C 평면도를 참조하지 않음 |
| 가상 센서 강제 상승 | SENSOR_MODE 등으로 데모·실장치 구분 | 운영 모드에서 실측 수치를 덮어쓰지 않음 |
| 프레임·analysis 재사용 | 매 반복 결과 초기화, 프레임 시간·번호 및 stale 판정 | 카메라 단절 시 이전 화재·안전 결과를 새 결과처럼 사용하지 않음 |
| call_ollama_native 인자 변경 | 기존 is_emergency=True 호출을 provider의 emergency=True로 전환 | TypeError 없이 fallback 동작 |
| PPASO 모델 자원 없음 | 다운로드 도구로 런타임·가중치 준비, initialized와 합성 확인 | 실제 한국어 WAV 생성·재생 성공 |
| 사이렌 종료가 pygame mixer.quit 호출 | 오디오 소유·재초기화 순서 정리 | 사이렌 종료 후 TTS 재생 유지 |
| 기존 테스트가 오류 dict도 성공 처리 | 오류 상태·기대 결과 assert와 실패 종료 코드 적용 | 실패 케이스가 테스트 실패로 집계 |

## 단계별 작업

### 0. 기준선 고정

- 실제 Git checkout과 현재 파일 스냅샷의 대응 관계 확인.
- 현재 코드·모델·데이터·설정의 복구 가능한 기준선 확보.
- 비교한 RAG 커밋을 통합 기준으로 고정하고 착수 시 브랜치 변경 여부 확인.
- Windows import 오류와 비전 확정 조건을 고친 뒤 현재 비전 테스트를 기준선으로 기록.

### 1. RAG만 통합

- RAG 필수 모듈, 질의 경로, provider 설정 이식.
- 새로운 main.py 호출 계약으로 텍스트 질문과 자동 경보를 연결.
- 기존 FAISS/BM25/메타데이터를 백업하고 인덱스 재구축.
- 로컬 모드에서 검색·근거·구역 경로를 확인한 뒤 설정된 클라우드 모드 검증.
- BGE는 feature/RAG 기본값인 비활성화로 시작하고 품질·지연 비교 후 활성화 여부 결정.

### 2. TTS 통합

- PPASO 자원 준비, feature/RAG의 TTS 코드 및 텍스트 처리 반영.
- 합성·재생·발화 완료·중단·종료 확인.
- 사이렌과 TTS 자원 충돌 해결.
- 긴급 첫 안내와 추가 안내, 반복 방송의 순서 검증.
- 모델 누락 시 조용히 성공 표시하지 않도록 실제 사용 엔진·실패 상태 표시.

### 3. STT 통합

- 캐시 우선 로딩 및 listen_once 호출 경로 반영.
- Windows에서 마이크 입력 → 검색 → 답변 → TTS 전체 경로 확인.
- Raspberry Pi의 기본 비활성화 설정은 독립적으로 다룬다. 장치 안정성과 추론 자원 확인 후 활성화한다.
- STT_WHISPER_MODEL을 배포 설정으로 관리하고 실제 장치에서 모델별 정확도·지연·메모리 측정 후 선택한다.
- 마이크 없음·모델 없음·오디오 초기화 실패는 텍스트 모드로 복귀한다.
- TTS 출력이 STT 입력에 들어가 반복 질문을 만들지 않는지 확인한다.

### 4. 통합 실행과 Pi 검증

- 이벤트 큐, 우선순위, 요청 결과 폐기, 경보 래치·해제, 종료 절차 구현.
- YOLO·임베딩·Ollama·TTS·STT 동시 실행 시 CPU/메모리와 감시 간격을 측정.
- 감시·검색·답변·음성의 시간을 분리 기록.
- 반복 사용과 장시간 감시에서 큐 적체·메모리 증가·카메라 단절 복구 확인.

### 5. GUI 확장 (후속)

feature/RAG의 Streamlit GUI를 가져오려면 gui/workers.py에 현재 비전 경로를 별도로 연결한다. CLI 통합이 완료되기 전에는 GUI의 기존 감시 작업자가 현재 비전 구현을 덮어쓰지 않게 한다.

## 검증 시나리오와 완료 기준

| 시나리오 | 기대 결과 |
|---|---|
| 정지 사진 첫 프레임·후속 프레임 | 모션 검증 전 경보가 발생하지 않음 |
| 사진 흔들림·실제 불꽃·상방 연기 | 현재 비전 방어 기능 보존, 연기 조기 감지 상태 유지 |
| 일반 답변 중 화재 | 감시 지속, 일반 발화 중단, 첫 비상 안내 우선 |
| Gemini 실패·Ollama 실패 | 공급자 전환, 최종 고정 안내 |
| 잘못된 구역·구역 미지정 | 무작위 대피로 생성 없음 |
| 감지 해제 후 지연 답변 도착 | 과거 경보 답변 재방송 없음 |
| 마이크·TTS 모델 없음 | 명확한 상태 표시와 사용 가능한 입력·출력 유지 |
| 사이렌 종료·연속 안내 | 오디오 장치 충돌 없이 한국어 발화 |
| 카메라 연결 끊김 | 오래된 프레임을 최신 정상 관측으로 취급하지 않음 |
| 데모 모드와 운영 모드 | 센서 강제 상승은 데모에서만 적용 |
| 문서·인덱스 변경 | 재구축 후 검색 근거 일치, 이전 인덱스 복구 가능 |

반응 시간은 가정한 모델 지연으로 계산하지 않는다. 실제 새 프레임 시각 → 감지 확정 → 경보 요청 → 첫 음성 시작의 단계별 시간을 측정하고, 중앙값과 p95, 감시 최대 공백, 최대 메모리를 기록한다. 수치 목표는 대상 Pi 환경의 기준선 측정 후 확정한다.

## 이번 비교의 검증 결과

- feature/RAG의 `python -B -m unittest discover -s tests -v`: 35개 통과.
- provider 테스트의 API 동작은 mock으로 확인했다. 실제 Gemini·Ollama 통신 성능을 검증한 결과는 아니다.
- TTS 테스트는 텍스트 처리·벤치마크 보조 동작을 검증한다. 실제 PPASO 합성·마이크·스피커 작동 검증은 아니다.
- 이전 프로젝트 분석에서 현재 모션 5개·퓨전 5개 테스트를 분리 실행해 통과했다.
- 현재 비전은 아직 위의 확정 조건·데이터 계약 문제를 갖는다. 기존 테스트 통과만으로 통합 완료 처리하지 않는다.

1차 통합 완료는 현재 비전 경로에서 텍스트 및 음성 질문이 feature/RAG를 통해 답변·발화되고, 느린 생성·공급자 실패·오디오 실패 중에도 감시와 첫 경보가 유지되는 상태다. Pi STT는 별도 장치 검증을 통과해야 완료로 표시한다.
