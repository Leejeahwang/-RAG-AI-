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

def call_ollama_native(prompt, system_prompt="", context="", question="", is_emergency=False):
    """requests를 사용하여 Ollama에 직접 스트리밍 요청을 보냅니다. (Chat API 사용)"""
    url = f"{config.OLLAMA_BASE_URL}/api/chat"
    
    if is_emergency:
        # 긴급 화재 안내를 위한 극단적 요약 프롬프트
        combined_prompt = (
            "너는 재난 대응 전문가인 '엣지 세이버'야. 화재 상황이 발생했어.\n"
            "제공된 [참고 매뉴얼]을 바탕으로 아래의 3가지 항목 형식으로만 답변을 작성해.\n"
            "인사말, 주의 문구, 부가 설명 등 잡다한 군더더기 내용은 전부 생략하고, 오직 아래 번호의 형식으로만 간결하게 한두 문장씩 작성해줘.\n\n"
            "1. 화재 발생, 화재 발생 종류, 화재 발생 장소\n"
            "2. 종류에 맞는 화재 대치 방법, 관련 소방 제품 위치\n"
            "3. 대피경로, 대피로\n\n"
            f"[참고 매뉴얼]\n{prompt}\n\n"
            f"상황 질문: {question}\n\n"
            "답변:"
        )
    else:
        # [호환성 패치] 시스템 프롬프트를 지원하지 않는 커스텀/소형 모델을 위해 모든 프롬프트를 user role 1개로 통합
        combined_prompt = (
            "너는 재난 대응 전문가인 '엣지 세이버'야. 제공된 [참고 매뉴얼]을 바탕으로 질문에 대해 충실하게 답변해.\n\n"
            "[수칙]\n"
            "1. (필수) 매뉴얼에 있는 [출처], [위치] 메타데이터나 불필요한 마크다운 기호(###, ---)는 출력하지 마.\n"
            "2. 긴급한 '대피/대처' 질문에는 핵심 결론부터 짧고 강하게 답변해.\n"
            "3. 모든 답변은 음성으로 읽기 좋게 문장형(-습니다, -에요)으로 작성해.\n"
            "4. (매우 중요) 답변을 마치면 즉시 대화를 종료하고, 사용자의 질문이나 프롬프트를 절대로 앵무새처럼 다시 따라 읽지 마.\n\n"
            f"[참고 매뉴얼]\n{prompt}\n\n"
            f"질문: {question}"
        )

    messages = [
        {"role": "user", "content": combined_prompt}
    ]

    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": "24h",
        "options": {
            "temperature": 0.1,
            "repeat_penalty": 1.15,   # [Option A 적용] 무한 반복 앵무새 버그를 억제하기 위해 페널티 재강화
            "num_predict": 800,       # [길이 제한 해제] 긴 매뉴얼 답변이 잘리지 않도록 300자에서 800자로 대폭 확장
            "num_ctx": 2048,
            "num_thread": 4,
            "use_mlock": True
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
                    # Chat API는 response 대신 message.content 안에 토큰이 들어있습니다.
                    # [호환성 패치] Qwen 추론 모델(DeepSeek-R1 Distill 등)의 경우 "thinking" 필드로 출력될 수 있습니다.
                    msg = chunk.get("message", {})
                    token = msg.get("content", "")
                    thinking_token = msg.get("thinking", "")
                    
                    if thinking_token:
                        yield thinking_token
                    elif token:
                        yield token
                        
                    if chunk.get("done", False):
                        break
    except Exception as e:
        yield f"[시스템 에러] 통신 실패: {e}"

def load_llm():
    """호환성을 위해 남겨둔 함수 (실제로는 call_ollama_native 사용)"""
    return None
