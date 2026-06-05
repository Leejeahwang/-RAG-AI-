"""
QA 시스템 (v35 Native)
LangChain 없이 직접 Ollama와 통신하여 속도를 극대화합니다.
"""
import requests
import json
import config

SYSTEM_PROMPT = """You are an emergency response expert 'Edge Saver'.
Your ONLY task is to copy and paste the relevant guidelines from the [참고 매뉴얼] exactly as they are written.

[Rules]
1. Copy the manual sentences verbatim. Do NOT change any words, endings, or sentence structures.
2. Do NOT summarize, modify, or rewrite any facts.
3. Output ONLY the copied emergency guidelines without any intro, extra explanations, or conversational filler.
4. Exclude metadata such as [출처], [위치] and markdown symbols (###, ---).

[참고 매뉴얼]
{context}

질문: {question}

답변:"""

def call_ollama_native(prompt, system_prompt="", context="", question=""):
    """requests를 사용하여 Ollama에 직접 스트리밍 요청을 보냅니다. (Chat API 사용)"""
    url = f"{config.OLLAMA_BASE_URL}/api/chat"
    
    # 0.5B 모델의 지능에 맞추어 시스템 역할(System Role)과 사용자 역할(User Role)을 분리하여 지침 수행력 향상
    system_content = (
        "You are an emergency response assistant 'Edge Saver'.\n"
        "Your ONLY task is to copy and paste the relevant instructions from the provided [참고 매뉴얼] exactly as they are written.\n"
        "Rules:\n"
        "1. Copy the manual sentences verbatim. Do NOT change any words, endings, or sentence structures.\n"
        "2. Do NOT summarize, modify, or rewrite any facts.\n"
        "3. Output ONLY the copied emergency guidelines without any intro, extra explanations, or conversational filler."
    )
    
    user_content = (
        f"[참고 매뉴얼]\n{prompt}\n\n"
        f"질문: {question}"
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]

    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": "24h",
        "options": {
            "temperature": 0.0,       # 0.5b의 횡설수설 방지를 위해 완전 확정적 생성(0.0) 유도
            "repeat_penalty": 1.05,   # 초경량 모델의 단어 왜곡(예: 메인 전원->전원콘)을 방지하기 위해 패널티 대폭 완화
            "num_predict": 400,       # 0.5b 가속을 위해 불필요하게 늘어나는 토큰 한도를 400자로 제한
            "num_ctx": 2048,
            "num_thread": 4,
            "use_mlock": True,
            "stop": ["질문:", "답변:", "수칙:", "매뉴얼:", "\n\n\n", "edgesaver", "edge saver"] # 앵무새 무한 루프 원천 차단 시퀀스 지정
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
