"""
QA 시스템 (v35 Native)
LangChain 없이 직접 Ollama와 통신하여 속도를 극대화합니다.
"""
import requests
import json
import config

SYSTEM_PROMPT = """너는 재난 전문가 '엣지 세이버'야. 매뉴얼을 근거로 짧고 강하게 답변해.
[수칙] 1. 메타데이터와 마크다운 기호 금지 2. 문장형(-습니다) 사용 3. 불필요한 서론 생략.

[매뉴얼] {context}
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
            "temperature": 0.1,
            "repeat_penalty": 1.2,
            "num_predict": 300,       # [최적화] 빠른 답변 생성을 위해 출력 길이 제한
            "num_ctx": 1024,          # [최적화] CPU 연산 부하를 줄이기 위해 문맥 길이 축소
            "num_thread": 4           # 라즈베리파이 5 코어 수에 맞춤
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
