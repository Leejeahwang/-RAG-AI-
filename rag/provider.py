"""로컬 매뉴얼 검색 결과를 Gemini 또는 Ollama로 답변한다."""

from dataclasses import dataclass
import logging
import re
import threading
import time

import requests

import config
from rag.chain import call_ollama_native

_LOG = logging.getLogger(__name__)
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_failure_until = 0.0
_failure_lock = threading.Lock()
_mode_lock = threading.Lock()
_MODE_LABELS = {"auto": "자동", "gemini": "Gemini 우선", "local": "로컬 고정"}

EMERGENCY_GUIDANCE = (
    "화재 위험이 감지되었습니다. 안전한 대피가 가능하면 즉시 대피하십시오. "
    "대피가 어렵다면 119에 현재 위치를 알리고 구조를 요청하십시오."
)


@dataclass(frozen=True)
class GuidanceResult:
    text: str
    provider: str
    fallback_reason: str = ""


def get_ai_mode() -> str:
    """현재 프로세스의 답변 공급자 모드를 반환한다."""
    with _mode_lock:
        return config.AI_PROVIDER


def set_ai_mode(mode: str) -> str:
    """실행 중 모드를 전환한다. 이미 시작한 요청은 기존 모드로 마친다."""
    global _failure_until
    normalized = mode.strip().lower()
    if normalized == "api":
        normalized = "gemini"
    if normalized not in _MODE_LABELS:
        raise ValueError("AI 모드는 auto, api(gemini), local 중 하나여야 합니다")
    with _mode_lock:
        config.AI_PROVIDER = normalized
    with _failure_lock:
        _failure_until = 0.0
    return normalized


def ai_mode_label(mode: str | None = None) -> str:
    return _MODE_LABELS.get(mode or get_ai_mode(), "알 수 없음")


def mode_command_response(command: str) -> str | None:
    """CLI의 /ai 명령을 처리하며, 일반 질문이면 None을 반환한다."""
    parts = command.strip().split()
    if not parts or parts[0].lower() != "/ai":
        return None
    if len(parts) == 1:
        return f"현재 AI 모드: {ai_mode_label()} (/ai auto | api | local)"
    if len(parts) != 2:
        return "사용법: /ai auto | api | local"
    try:
        mode = set_ai_mode(parts[1])
    except ValueError:
        return "사용법: /ai auto | api | local"
    if mode == "gemini" and not config.GEMINI_API_KEY:
        return "Gemini 우선 모드로 변경했습니다. API 키가 없어 요청 시 로컬로 전환됩니다."
    return f"AI 모드 변경: {ai_mode_label(mode)} (다음 요청부터 적용)"


def _clean_for_match(value: str) -> str:
    """Ignore presentation markup while preserving words, numbers and negation."""
    lines = []
    for line in value.splitlines():
        line = re.sub(r"^\s*(?:[-*•]\s+|\d+[.)]\s+|#{1,6}\s+)", "", line)
        line = re.sub(r"[*`\"'‘’“”]", "", line)
        lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _is_grounded(answer: str, context: str) -> bool:
    """Allow formatting differences; require the cited words to remain in the manual."""
    source = _clean_for_match(context)
    lines = [_clean_for_match(line) for line in answer.splitlines() if line.strip()]
    lines = [line for line in lines if line]
    return bool(lines) and all(re.search(r"(?<!\S)" + re.escape(line) + r"(?!\w)", source) for line in lines)


def _call_gemini(context: str, question: str, require_quotes: bool = False) -> str:
    model = config.GEMINI_MODEL
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
        raise ValueError("Gemini 모델명 형식이 올바르지 않습니다")
    response_style = (
        "질문에 관련된 문장을 원문 그대로 한 줄씩 인용하십시오. "
        if require_quotes else
        "질문에 관련된 내용을 요약하고 자연스러운 한국어로 바꾸어 설명해도 됩니다. "
        "핵심 행동을 짧은 항목으로 안내하십시오. "
    )
    payload = {
        "systemInstruction": {"parts": [{"text": (
            "당신은 화재 대응 매뉴얼 안내자입니다. 참고 매뉴얼만 근거로 답하십시오. "
            + response_style +
            "없는 사실, 장소, 대피로를 만들지 마십시오. 숫자, 장소, 조건과 금지 사항을 바꾸지 마십시오. "
            "관련 내용이 없으면 빈 답변을 반환하십시오."
        )}]},
        "contents": [{"role": "user", "parts": [{"text":
            f"[참고 매뉴얼]\n{context}\n\n[질문]\n{question}"
        }]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 400},
    }
    response = requests.post(
        _GEMINI_URL.format(model=model),
        headers={"x-goog-api-key": config.GEMINI_API_KEY},
        json=payload,
        timeout=(config.GEMINI_CONNECT_TIMEOUT, config.GEMINI_READ_TIMEOUT),
    )
    response.raise_for_status()
    candidates = response.json().get("candidates") or []
    if not candidates:
        raise ValueError("Gemini 답변이 비어 있습니다")
    first = candidates[0]
    finish_reason = first.get("finishReason")
    if finish_reason not in (None, "STOP"):
        # Log only the API's enum, never response text or request credentials.
        reason = finish_reason if isinstance(finish_reason, str) and re.fullmatch(r"[A-Z_]{1,40}", finish_reason) else "UNKNOWN"
        raise ValueError(f"Gemini 답변이 완료되지 않았습니다: {reason}")
    parts = first.get("content", {}).get("parts") or []
    answer = "".join(part.get("text", "") for part in parts).strip()
    if not answer:
        raise ValueError("Gemini 답변이 비어 있습니다")
    if require_quotes and not _is_grounded(answer, context):
        raise ValueError("Gemini 답변이 매뉴얼 원문과 일치하지 않습니다")
    return answer


def _local(context: str, question: str, emergency: bool) -> str:
    timeout = (2, config.OLLAMA_EMERGENCY_TIMEOUT) if emergency else None
    answer = "".join(call_ollama_native(prompt=context, question=question, timeout=timeout)).strip()
    if not answer:
        raise ValueError("Ollama 답변이 비어 있습니다")
    return answer


def generate_guidance(
    context: str,
    question: str,
    emergency: bool = False,
    cloud_context: str | None = None,
) -> GuidanceResult:
    """API 실패 시 로컬로 전환하고, 긴급 상황에선 고정 안내를 최후 수단으로 사용한다."""
    global _failure_until
    mode = get_ai_mode()
    if mode not in ("auto", "gemini", "local"):
        raise ValueError(f"알 수 없는 AI_PROVIDER: {mode}")
    remote_context = context if cloud_context is None else cloud_context
    fallback_reason = ""
    if mode != "local" and not config.GEMINI_API_KEY:
        fallback_reason = "Gemini API 키 없음"
    elif mode != "local" and mode == "auto" and time.monotonic() < _failure_until:
        fallback_reason = "Gemini 재시도 대기 중"
    elif mode != "local" and not remote_context.strip():
        fallback_reason = "전송 가능한 매뉴얼 없음"
    elif mode != "local":
        try:
            answer = _call_gemini(remote_context, question, require_quotes=emergency)
            with _failure_lock:
                _failure_until = 0.0
            return GuidanceResult(answer, "gemini")
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            fallback_reason = type(exc).__name__
            detail = ""
            if isinstance(exc, ValueError):
                message = str(exc)
                known_messages = {
                    "Gemini 모델명 형식이 올바르지 않습니다",
                    "Gemini 답변이 비어 있습니다",
                    "Gemini 답변이 매뉴얼 원문과 일치하지 않습니다",
                }
                if message in known_messages or re.fullmatch(r"Gemini 답변이 완료되지 않았습니다: [A-Z_]{1,40}", message):
                    detail = f": {message}"
                else:
                    detail = ": Gemini 응답 JSON 해석 또는 값 처리 실패"
            _LOG.warning("Gemini 사용 실패 (%s%s), Ollama로 전환", fallback_reason, detail)
            if mode == "auto":
                with _failure_lock:
                    _failure_until = time.monotonic() + config.GEMINI_RETRY_COOLDOWN
    try:
        answer = _local(context, question, emergency)
        if emergency and not _is_grounded(answer, context):
            return GuidanceResult(EMERGENCY_GUIDANCE, "fixed", "로컬 답변 근거 불충분")
        return GuidanceResult(answer, "ollama", fallback_reason)
    except Exception as exc:
        _LOG.warning("Ollama 사용 실패 (%s)", type(exc).__name__)
        if emergency:
            return GuidanceResult(EMERGENCY_GUIDANCE, "fixed", fallback_reason or type(exc).__name__)
        raise
