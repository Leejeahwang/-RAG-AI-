# RAG 검색 예비 비교

```bash
python tools/benchmark_rag.py --repeats 3
```

현재 실행 중인 Python 환경에서 측정한다. CPU, 기존 `faiss_db` 문서·벡터와 캐시된 임베딩 모델이 필요하다. Chroma 비교에는 `chromadb`, `langchain-community`도 필요하다. 측정 중 Hugging Face 다운로드는 차단한다. 기존 검색 인덱스는 수정하지 않는다.

출력은 `scratch/rag_benchmark/날짜_시간/`의 `comparison.json`, `comparison.csv`와 케이스별 `result.json`, `worker.log`다. 케이스별 별도 프로세스를 순차 실행한다. 기본 제한 시간은 각 300초이고 `--timeout`으로 변경한다.

| 케이스 | 검색 구성 |
|---|---|
| `chroma` | LangChain Chroma + 동일 Sentence-Transformers 질문 임베딩 |
| `native` | 현재 FAISS + BM25 + RRF + 규칙 정렬, BGE 재정렬 제외 |
| `native_rerank` | 현재 구성 전체, BGE 재정렬 포함 |

문서 벡터를 새로 생성하지 않고 기존 FAISS 벡터를 Chroma에 넣는다. Chroma 기본 L2 거리 검색과 FAISS의 L2 거리 검색을 사용한다. 모든 케이스에 같은 질문 4개를 각 1회 준비 실행하고, 이후 설정한 횟수만큼 반복해 질문별 중앙값·최소값·최대값을 기록한다. 검색 시간에는 질문 임베딩 생성과 문서 검색·필터링·선택한 재정렬을 포함하며 LLM·TTS는 제외한다.

## 해석 시 주의

- 이는 이전 프로젝트 전체를 그대로 복원한 시험이 아니다. 과거 코드의 Ollama 임베딩을 현재와 같은 Sentence-Transformers로 맞춰 비교한 기준 구성이다.
- 공통 준비 경로를 맞추기 위해 Chroma 케이스도 현재 FAISS 인덱스와 BM25를 로드한 상태에서 실행한다. 메모리는 이 공통 준비 상태에 Chroma 구성까지 포함한다. 실제 Chroma 단독 배포 메모리로 해석하면 안 된다.
- 메모리는 프로세스 초기화·준비 실행·검색 전체에서 Windows는 10ms 표본 RSS 최대값, Linux는 표본 RSS와 ru_maxrss의 최대값이다. 모델과 Python·라이브러리까지 포함하며 시스템 전체 메모리는 아니다.
- Chroma는 의미 검색이고 현재 구현에는 키워드 검색과 규칙이 추가된다. 속도가 비슷하거나 빨라도 검색 품질이 같다는 뜻은 아니다. 검색된 출처를 저장하지만 정답 평가 점수는 계산하지 않는다.
- `native_rerank`와 `native` 비교는 현재 BGE 재정렬 단계의 부담을 확인하기 위한 것이다. 재정렬을 끈 결과를 현재 기본 구성의 성능으로 발표하면 안 된다.
- Chroma 데이터 구축 시간은 별도 기록하고 반복 검색 시간에서 제외한다. 현재 구현의 로딩 시간도 따로 기록한다. 초기화 시간으로 완전한 콜드 부팅 비용을 주장하지 않는다.
- FAISS IndexFlatL2와 Chroma 기본 HNSW는 인덱스 방식이 다르다. 소규모 문서에서의 결과를 대규모 검색 성능으로 일반화하지 않는다.
- 현재 PC에서 실행하면 Windows 측정이다. 라즈베리파이 성능을 주장하려면 같은 프로그램을 Pi에서 별도 실행해야 한다.

필요한 케이스만 선택할 수 있다.

```bash
python tools/benchmark_rag.py --cases chroma native --repeats 5
python tools/benchmark_rag.py --cases native native_rerank --repeats 5
```

## 검색 품질 비교

```bash
python tools/benchmark_rag.py --quality --cases native native_rerank --repeats 2 --timeout 900
```

비교 프로그램은 기본적으로 `--reranker-policy full`로 BGE 전체 적용을 측정한다. 운영 설정의 선택적 재정렬을 확인하려면 `--reranker-policy selective`를 추가한다. 명확한 CPR·출혈·골절 의도에 맞는 근거 후보가 확보되면 의료 경로에서 BGE 추론을 생략한다. 의료 의도가 불명확하거나 근거가 없는 경우, 구역·화재 등 다른 질문은 BGE를 계속 사용한다. 모델은 여전히 미리 로드하므로 선택적 추론 생략이 메모리 절감을 의미하지는 않는다.

`tools/rag_quality_dataset.py`에 미리 정의한 28개 질문(구역 6, 의료 8, 공장 8, 아파트 4, 산악 2)을 평가한다. 기대 출처와 근거 표현 그룹을 모두 만족하는 청크를 정답 후보로 지정하며, 청크의 출처·내용 SHA-256을 저장한다. 정답 후보가 없는 질문은 평가를 중단한다. 반환된 상위 2개를 정답 청크 ID와 비교해 Hit@1, Hit@2, MRR@2를 기록한다. 반복 모두에 적중해야 질문의 Hit가 참이다.

품질 모드에서는 첫 질문만 준비 실행하고 이후 모든 질문을 반복 측정한다. 질문별 최초 실행 비용이 일부 포함될 수 있다. 이는 소규모 내부 근거 검색 시험이며 독립적인 사람 평가, 최종 답변 정확성, 의료·화재 지침의 안전성 평가는 아니다. 기존 수정 확인 질문과 새로운 질문이 섞여 있으므로 독립적인 외부 평가 점수로 표현하지 않는다. `quality_gold.json`과 `result.json`이 상세 근거를 보존한다. 같은 인덱스 해시와 정답 후보인지 확인한 뒤 비교해야 한다.
