"""
QA 시스템 (v35 Native)
LangChain 없이 직접 Ollama와 통신하여 속도를 극대화합니다.
"""
import requests
import json
import config

SYSTEM_PROMPT = """너는 재난 대응 전문가인 '엣지 세이버'야.
제공된 [참고 매뉴얼]을 바탕으로 질문에 대해 충실하게 답변해.

[수칙]
1. (필수) 매뉴얼에 있는 [출처], [위치] 메타데이터나 불필요한 마크다운 기호(###, ---)는 출력하지 마.
2. 긴급한 '대피/대처' 질문에는 핵심 결론부터 짧고 강하게 답변하고, '기준/원리' 같은 기술적 질문에는 매뉴얼의 내용을 상세히 포함해서 설명해.
3. 모든 답변은 음성으로 읽기 좋게 문장형(-습니다, -에요)으로 작성하고, 복잡한 표 형태보다는 리스트(1., 2.)로 풀어서 써줘.

[참고 매뉴얼]
{context}

질문: {question}

답변:"""

def call_ollama_native(prompt):
    """requests를 사용하여 Ollama에 직접 스트리밍 요청을 보냅니다."""
    url = f"{config.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": config.LLM_MODEL,
        "prompt": prompt,
        "stream": True,
        "keep_alive": "24h",  # 한 번 메모리에 올린 모델을 24시간 동안 내리지 않음 (최초 로딩 이후 지연 시간 완전 제거)
        "options": {
            "temperature": 0.0,       # 샘플링 연산 최소화 및 답변 일관성(품질) 극대화
            "repeat_penalty": 1.2,
            "num_predict": 300,
            "num_ctx": 2048,          # 6개의 지식이 온전히 들어가 품질을 유지하도록 다시 확장
            "num_thread": 4
        }
    }
    
    try:
        # 라즈베리파이 환경을 고려하여 타임아웃을 300초(5분)로 연장
        with requests.post(url, json=payload, stream=True, timeout=300) as response:
            if response.status_code != 200:
                yield f"[시스템 에러] Ollama 서버 응답 실패 ({response.status_code})"
                return
                
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done", False):
                        break
    except Exception as e:
        yield f"[시스템 에러] 통신 실패: {e}"

def load_llm():
    """호환성을 위해 남겨둔 함수 (실제로는 call_ollama_native 사용)"""
    return None
