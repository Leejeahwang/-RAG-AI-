"""
QA 시스템 (v35 Native)
LangChain 없이 직접 Ollama와 통신하여 속도를 극대화합니다.
"""
import requests
import json
import config

SYSTEM_PROMPT = """재난 대응 전문가 엣지 세이버의 비상 지시서.

[현장 구역 대피 경로 정보]
{zone_context}

[보조 소방 요령]
{general_context}

[지시]
위의 [현장 구역 대피 경로 정보]에 적혀 있는 대피로 내용을 있는 그대로 첫 문장으로 낭독하여 답변하십시오.

답변:"""

SYSTEM_PROMPT_NORMAL = """재난 대응 전문가 엣지 세이버의 소방 지식 AI 가이드.

[보조 소방 요령 및 참고 매뉴얼]
{general_context}

[사용자 질문]
{question}

위의 [보조 소방 요령 및 참고 매뉴얼]을 근거로 삼아, 사용자의 질문에 대해 핵심만 요약하여 정중하고 명확하게 답변하십시오. 답변에 `[보조 소방 요령]` 이나 `[지시]`와 같은 프롬프트 내부 지시 태그를 반복하지 마십시오.

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
            "num_predict": 512,       # 답변이 중간에 길게 잘리지 않도록 토큰 허용치 2배 증가
            "num_ctx": 2048,          # 검색된 문서가 충분히 다 들어갈 수 있도록 문맥 길이 확장
            "num_thread": 8
        }
    }
    
    try:
        with requests.post(url, json=payload, stream=True, timeout=60) as response:
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
