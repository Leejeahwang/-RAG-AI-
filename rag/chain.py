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
3. 모든 답변은 음성으로 읽기 좋게 공식적인 존댓말인 문장형(-해야 합니다, -입니다, -하십시오)으로 작성하고, 복잡한 표 형태보다는 리스트(1., 2.)로 풀어서 써줘.

[참고 매뉴얼]
{context}

질문: {question}

답변:"""

def call_ollama_native(prompt, system_prompt="", context="", question=""):
    """requests를 사용하여 Ollama에 직접 스트리밍 요청을 보냅니다. (Chat API 사용)"""
    url = f"{config.OLLAMA_BASE_URL}/api/chat"
    
    # [호환성 패치] 시스템 프롬프트를 지원하지 않는 커스텀/소형 모델을 위해 모든 프롬프트를 user role 1개로 통합
    combined_prompt = (
        "너는 재난 대응 전문가인 '엣지 세이버'야. 제공된 [참고 매뉴얼]을 바탕으로 질문에 대해 충실하게 답변해.\n\n"
        "[수칙]\n"
        "1. (필수) 매뉴얼에 있는 [출처], [위치] 메타데이터나 불필요한 마크다운 기호(###, ---)는 출력하지 마.\n"
        "2. 긴급한 '대피/대처' 질문에는 핵심 결론부터 짧고 강하게 답변해.\n"
        "3. 모든 답변은 음성으로 읽기 좋게 공식적인 문장형 존댓말(-해야 합니다, -입니다, -하십시오)으로 작성해.\n"
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

def rewrite_query_ollama(query):
    """소형 모델을 사용하여 구어체/다급한 질문을 고속으로 RAG 검색 전용 핵심 명사 키워드로 변환합니다."""
    import requests
    import json
    import re
    url = f"{config.OLLAMA_BASE_URL}/api/generate"
    prompt = (
        "당신은 재난 안전 전문 검색어 보조 장치입니다.\n"
        "다급하거나 풀어 써진 구어체 질문을 RAG 정보 검색에 적합한 표준 명사형 키워드 2~3개로 정밀 변환하십시오.\n"
        "이때 질문의 어미나 구어적 표현은 완전히 배제하고, 반드시 다음 사상(Mapping)을 강제 적용하십시오:\n"
        "- '불', '불이 났는데', '불남' -> '화재, 대피'\n"
        "- '숨', '숨을 안쉬어', '안쉼', '숨안쉼', '심정지' -> '심폐소생술, CPR, 응급처치'\n"
        "- '피나', '피남', '다침' -> '지혈, 응급처치'\n"
        "설명 없이 오직 쉼표로 구분한 단답 명사들만 출력하십시오.\n\n"
        f"질문: {query}\n"
        "키워드:"
    )
    payload = {
        "model": config.KEYWORD_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "repeat_penalty": 1.2,
            "num_predict": 20,
            "num_thread": 4
        }
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            result = response.json().get("response", "").strip()
            # 쉼표나 단어가 깨지는 것을 방지하고 줄바꿈 제거
            cleaned = result.replace("\n", " ").strip()
            
            # [안전 장치] 소형 모델의 설명조 문구 및 지침 반복 출력 강제 필터링
            for phrase in ["쉼표로 출력합니다", "쉼표로 구분하여", "명사 키워드는", "키워드는", "추출된 키워드", "핵심 키워드", "입니다", "출력합니다"]:
                cleaned = cleaned.replace(phrase, "")
            
            # 한글, 영문, 숫자, 쉼표, 공백 외의 모든 불필요한 기호 제거
            cleaned = re.sub(r'[^가-힣a-zA-Z0-9\s,]', '', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            
            # 마침표 제거
            if cleaned.endswith("."):
                cleaned = cleaned[:-1]
            return cleaned.strip()
    except Exception as e:
        pass
    return ""
