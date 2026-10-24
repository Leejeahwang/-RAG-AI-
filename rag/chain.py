"""
QA 시스템 (v35 Native)
LangChain 없이 직접 Ollama와 통신하여 속도를 극대화합니다.
"""
import requests
import json
import logging
import time
import config

_LOGGER = logging.getLogger(__name__)

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

def call_ollama_native(prompt, system_prompt="", context="", question="", timeout=None,
                       response_format=None, num_predict=400):
    """requests를 사용하여 Ollama에 직접 스트리밍 요청을 보냅니다. (Chat API 사용)"""
    url = f"{config.OLLAMA_BASE_URL}/api/chat"
    
    # 0.5B 모델의 지능에 맞추어 시스템 역할(System Role)과 사용자 역할(User Role)을 분리하여 지침 수행력 향상
    system_content = (
        "You are an emergency response expert 'Edge Saver'.\n"
        "Your ONLY task is to copy and output the safety instructions from the [참고 매뉴얼] word for word. Do NOT change, summarize, or modify any words.\n\n"
        "Example:\n"
        "[참고 매뉴얼]\n"
        "* 전기 화재 시 절대로 물을 뿌리면 안 됩니다. 메인 차단기를 내리고 분말 소화기를 사용하십시오.\n"
        "질문: 전기 화재 대처법은?\n"
        "답변: 전기 화재 시 절대로 물을 뿌리면 안 됩니다. 메인 차단기를 내리고 분말 소화기를 사용하십시오.\n\n"
        "Ensure you answer ONLY with the copied manual lines without any extra comments."
    )
    
    user_content = (
        f"[참고 매뉴얼]\n{prompt}\n\n"
        f"질문: {question}"
    )

    messages = [
        {"role": "system", "content": system_prompt or system_content},
        {"role": "user", "content": user_content}
    ]

    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": "24h",
        "options": {
            "temperature": 0.1,       # 특정 루프 차단을 위한 약간의 유연성 부여
            "top_p": 0.85,            # 무작위 이상한 단어 생성을 억제하기 위한 누적 확률 제한
            "repeat_penalty": 1.15,   # 단어 반복 루프(1.05)와 억지 단어 비틀기(1.35) 사이의 최적의 밸런스 지점
            "num_predict": num_predict,
            "num_ctx": 2048,
            "num_thread": 4,
            "stop": ["질문:", "답변:", "수칙:", "매뉴얼:", "\n\n\n", "edgesaver", "edge saver"] # 앵무새 무한 루프 원천 차단 시퀀스 지정
        }
    }
    if response_format is not None:
        payload["format"] = response_format
    started = time.monotonic()
    _LOGGER.info("[Ollama] 요청 시작: 모델=%s, 최대 생성=%d토큰", config.LLM_MODEL, num_predict)
    
    try:
        # 라즈베리파이 환경을 고려하여 타임아웃을 300초(5분)로 연장
        with requests.post(url, json=payload, stream=True, timeout=timeout or 300) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Ollama 서버 응답 실패 ({response.status_code})")
                
            stream_done = False
            token_count = 0
            for line in response.iter_lines(chunk_size=1):
                if line:
                    chunk = json.loads(line.decode("utf-8"))
                    if chunk.get("error"):
                        raise RuntimeError("Ollama 스트림 오류 응답")
                    # Chat API는 response 대신 message.content 안에 토큰이 들어있습니다.
                    # [호환성 패치] Qwen 추론 모델(DeepSeek-R1 Distill 등)의 경우 "thinking" 필드로 출력될 수 있습니다.
                    msg = chunk.get("message", {})
                    token = msg.get("content", "")
                    thinking_token = msg.get("thinking", "")
                    
                    # thinking과 content가 같은 청크에 함께 오면 content를 우선한다.
                    # 기존 if/elif는 thinking이 존재할 때 실제 답변 content를 버릴 수 있었다.
                    if token:
                        if token_count == 0:
                            _LOGGER.info("[Ollama] 첫 응답 수신: %.2fs", time.monotonic()-started)
                        token_count += 1
                        yield token
                    elif thinking_token:
                        # content가 아직 없는 reasoning 청크는 사용자 답변/TTS에 내보내지 않는다.
                        pass
                        
                    if chunk.get("done", False):
                        if chunk.get("done_reason") == "length":
                            raise RuntimeError("Ollama 생성 토큰 한도 초과")
                        stream_done = True
                        break
            if not stream_done:
                raise RuntimeError("Ollama 스트림이 완료되지 않았습니다")
            _LOGGER.info("[Ollama] 응답 완료: %.2fs", time.monotonic()-started)
    except Exception as e:
        _LOGGER.exception("[Ollama] 스트리밍 요청/파싱 실패")
        raise RuntimeError(f"Ollama 스트리밍 실패: {e}") from e

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
        response = requests.post(url, json=payload, timeout=15)
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
