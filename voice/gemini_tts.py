"""Gemini TTS REST synthesis; credentials and response bodies are not logged."""
import base64
import io
import re
import wave
from pathlib import Path

import requests
import config


def synthesize_to_file(text, output_path):
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Gemini TTS API key unavailable")
    model = config.GEMINI_TTS_MODEL
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
        raise ValueError("Invalid Gemini TTS model")
    # 3.8 uses a verbatim transcript and structured voice selection.
    voice = {"voice": config.GEMINI_TTS_VOICE}
    if not model.startswith("gemini-3.8-"):
        voice = {"prebuiltVoiceConfig": {"voiceName": config.GEMINI_TTS_VOICE}}
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": config.GEMINI_API_KEY},
        json={
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": voice},
            },
        },
        timeout=(config.GEMINI_CONNECT_TIMEOUT, config.GEMINI_TTS_READ_TIMEOUT),
    )
    if not response.ok:
        raise RuntimeError(f"Gemini TTS HTTP {response.status_code}")
    candidates = response.json().get("candidates") or []
    if not candidates or candidates[0].get("finishReason") not in (None, "STOP"):
        raise ValueError("Gemini TTS incomplete audio response")
    parts = candidates[0].get("content", {}).get("parts") or []
    blocks = [part["inlineData"] for part in parts if "inlineData" in part]
    if not blocks:
        raise ValueError("Gemini TTS audio missing")
    mime = blocks[0].get("mimeType", "").lower()
    if any(block.get("mimeType", "").lower() != mime for block in blocks):
        raise ValueError("Gemini TTS mixed audio formats")
    data = b"".join(base64.b64decode(block["data"], validate=True) for block in blocks)
    if not data:
        raise ValueError("Gemini TTS empty audio")
    target = Path(output_path)
    if mime.split(";")[0] in {"audio/wav", "audio/x-wav"}:
        with wave.open(io.BytesIO(data), "rb") as audio:
            if not audio.getnframes() or audio.getsampwidth() != 2:
                raise ValueError("Gemini TTS invalid WAV")
        target.write_bytes(data)
    elif mime.startswith(("audio/l16", "audio/pcm")):
        rate_match = re.search(r"(?:^|;)\s*rate=(\d+)", mime)
        rate = int(rate_match.group(1)) if rate_match else 24000
        if len(data) % 2 or rate not in {8000, 16000, 22050, 24000, 44100, 48000}:
            raise ValueError("Gemini TTS invalid PCM")
        with wave.open(str(target), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(rate)
            audio.writeframes(data)
    else:
        raise ValueError("Gemini TTS unsupported audio format")
