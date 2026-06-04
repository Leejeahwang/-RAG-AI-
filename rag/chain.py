"""
QA 시스템 (v35 Native)
LangChain 없이 직접 Ollama와 통신하여 속도를 극대화합니다.
"""
import requests
import json
import config

SYSTEM_PROMPT = """너는 재난 대응 전문가인 '엣지 세이버'야.
제공된 [참고 매뉴얼]의 내용을 절대로 요약하거나 문장 의미를 임의로 재구성(변형)하지 말고, 원문 대처 수칙과 사실을 그대로 복제하여 제시하십시오.

[수칙]
1. (필수) 매뉴얼 원문 수칙 내용을 지어내거나 누락하지 말고 사실 그대로 정확하게 인용 출력하십시오.
2. 매뉴얼 내의 [출처], [위치] 메타데이터나 불필요한 마크다운 기호(###, ---)는 제외하고 출력하십시오.
3. 문장 어미는 음성 출력이 매끄럽도록 공식적인 문장형 존댓말(-해야 합니다, -입니다, -하십시오)로만 다듬어 완성하십시오.

[참고 매뉴얼]
{context}

질문: {question}

답변:"""

def call_ollama_native(prompt, system_prompt="", context="", question=""):
    """requests를 사용하여 Ollama에 직접 스트리밍 요청을 보냅니다. (Chat API 사용)"""
    url = f"{config.OLLAMA_BASE_URL}/api/chat"
    
    # [호환성 패치] 0.5B 모델의 지능에 맞추어 매뉴얼 복제 인용 및 존댓말 마감 수칙 적용
    combined_prompt = (
        "너는 재난 대응 전문가인 '엣지 세이버'야. 제공된 [참고 매뉴얼]의 수칙 내용을 임의로 생략하거나 문맥을 변형하지 말고 사실 그대로 복사 인용하여 제시하십시오.\n\n"
        "[수칙]\n"
        "1. 매뉴얼 원문의 사실적 대응 지침을 임의로 요약하거나 재구성하지 말고 그대로 출력하십시오.\n"
        "2. 매뉴얼에 명시된 [출처], [위치] 메타데이터 및 불필요한 마크다운 기호(###, ---)는 지우고 출력하십시오.\n"
        "3. 모든 문장 끝은 음성 출력이 좋게 공식적인 문장형 존댓말(-해야 합니다, -입니다, -하십시오)로 통일해 주십시오.\n"
        "4. 답변 완료 시 즉시 출력을 종료하고 불필요한 사설이나 사용자의 질문을 따라 읽지 마십시오.\n\n"
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
            "temperature": 0.0,       # 0.5b의 횡설수설 방지를 위해 완전 확정적 생성(0.0) 유도
            "repeat_penalty": 1.35,   # 초경량 모델의 반복 앵무새 꼬임 현상을 억제하기 위한 페널티 재강화
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
