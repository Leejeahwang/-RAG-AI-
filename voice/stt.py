"""
voice/stt.py — 하이브리드 오프라인 음성 인식(STT) 모듈
=========================================================
- Windows(Intel SST) 및 Linux(Raspberry Pi 5) 지원
- 자동 장치 감지, DC Offset 제거 및 문장 단위 버퍼링 기능
"""

import time
import threading
import numpy as np
import pyaudio
import platform
import os
import sys
from faster_whisper import WhisperModel

# ------------------------------------------------
# 시스템 설정
# ------------------------------------------------
IS_WINDOWS = platform.system() == "Windows"
MACHINE = platform.machine().lower()
IS_PI = "arm" in MACHINE or "aarch64" in MACHINE

MODEL_SIZE  = "base"      # 모델 크기 (base, small, medium 등)
DEVICE_TYPE = "cpu"       # 실행 장치 (cpu 또는 cuda)
COMPUTE     = "int8"      # 연산 정밀도
SAMPLE_RATE  = 48000      # 입력 샘플링 레이트
WHISPER_RATE = 16000      # Whisper 모델용 샘플링 레이트
CHUNK_SEC    = 0.5        # 처리 단위 (초)

STREAM_CHANNELS = 1
STREAM_FORMAT   = pyaudio.paInt16
STREAM_DEVICE   = None

SILENCE_THRESHOLD = 0.05  # 무음 감지 임계값
WAKE_WORDS      = ["세이버", "에이버", "세이 버", "세이바", "saver"] # 호출어
SILENCE_TIMEOUT = 1.5     # 무음 종료 대기 시간

# ------------------------------------------------
# 장치 및 스트림 관리
# ------------------------------------------------
def _get_pyaudio_instance():
    return pyaudio.PyAudio()

def _find_best_device(pa: pyaudio.PyAudio):
    """플랫폼(Win/Linux)에 따른 최적화된 마이크 장치 검색"""
    all_inputs = []
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            all_inputs.append(info)

    # 특정 하드웨어(예: X-PRO 마이크) 우선 검색
    for info in all_inputs:
        if "X-PRO" in info["name"]:
            return info['index'], 2

    if IS_WINDOWS:
        keywords = ["배열", "intel", "microphone", "마이크"]
    else:
        keywords = ["usb", "capture", "audio", "default", "hw:"]

    for kw in keywords:
        for info in all_inputs:
            name = info["name"].lower()
            if kw in name and "stereo mix" not in name and "loopback" not in name:
                print(f"[STT] 장치 선택됨: {info['name']} (인덱스 {info['index']})")
                return info['index'], int(info['maxInputChannels'])

    try:
        default_info = pa.get_default_input_device_info()
        print(f"[STT] 기본 장치 사용: {default_info['name']}")
        return default_info['index'], int(default_info['maxInputChannels'])
    except:
        pass
            
    return 0, 1

def _open_stream(pa: pyaudio.PyAudio) -> pyaudio.Stream:
    global STREAM_CHANNELS, STREAM_FORMAT, STREAM_DEVICE, SAMPLE_RATE
    device_idx, max_channels = _find_best_device(pa)
    STREAM_DEVICE = device_idx
    
    rates_to_try = [48000, 44100, 16000]
    channels_to_try = [max_channels] if max_channels <= 2 else [2, 1]
    if 1 not in channels_to_try: channels_to_try.append(1)

    print(f"[STT] 오디오 스트림 초기화 중...")
    for rate in rates_to_try:
        for ch in channels_to_try:
            try:
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=ch,
                    rate=rate,
                    input=True,
                    input_device_index=device_idx,
                    frames_per_buffer=4096
                )
                SAMPLE_RATE = rate
                STREAM_CHANNELS = ch
                print(f"[STT] 스트림 연결됨 ({rate}Hz, 16bit, {'Stereo' if ch==2 else 'Mono'})")
                return stream
            except:
                continue
    raise RuntimeError(f"[STT] 오디오 스트림을 열 수 없습니다.")

# ------------------------------------------------
# 오디오 처리 로직
# ------------------------------------------------
def _load_model() -> WhisperModel:
    print(f"[STT] 플랫폼: {'라즈베리 파이 5' if IS_PI else '노트북'}")
    print(f"[STT] faster-whisper 모델 로드 중 ({MODEL_SIZE})...", end=" ", flush=True)
    model = WhisperModel(MODEL_SIZE, device=DEVICE_TYPE, compute_type=COMPUTE)
    print("완료")
    return model

def _transcribe(model: WhisperModel, audio_np: np.ndarray) -> str:
    """오디오 데이터를 텍스트로 변환"""
    max_val = np.abs(audio_np).max()
    if max_val > 0.01:
        audio_np = audio_np / max_val * 0.9
        
    segments, _ = model.transcribe(
        audio_np, 
        language="ko", 
        beam_size=5,
        initial_prompt="안녕하세요. 오프라인 음성 인식 시스템입니다. 한국어로 침착하게 말씀해 주세요.",
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 700},
    )
    return " ".join(seg.text.strip() for seg in segments).strip()

def _record_chunk(stream: pyaudio.Stream, seconds: float = CHUNK_SEC, drain: bool = False) -> np.ndarray:
    """오디오 스트림에서 일정 단위의 청크를 읽어옴"""
    samples_needed = int(SAMPLE_RATE * seconds)
    
    STEP_SEC = 0.1
    STEP_SAMPLES = int(SAMPLE_RATE * STEP_SEC)
    
    buf = []
    read_so_far = 0
    
    try:
        if drain:
            while stream.get_read_available() > 0:
                stream.read(min(stream.get_read_available(), 4096), exception_on_overflow=False)

        while read_so_far < samples_needed:
            to_read = min(STEP_SAMPLES, samples_needed - read_so_far)
            if to_read <= 0: break
            
            chunk_data = stream.read(to_read, exception_on_overflow=False)
            buf.append(chunk_data)
            read_so_far += to_read
            
        full_raw = b"".join(buf)
        audio_f32 = np.frombuffer(full_raw, dtype=np.int16).astype(np.float32) / 32768.0
        
        # 스테레오 -> 모노 믹싱
        if STREAM_CHANNELS >= 2:
            audio_f32 = audio_f32.reshape(-1, STREAM_CHANNELS)[:, 0]
        
        # DC Offset 제거 (노이즈 감소)
        audio_f32 = audio_f32 - np.mean(audio_f32)
            
        # Whisper 호환 샘플링 레이트로 리샘플링
        if SAMPLE_RATE != WHISPER_RATE:
            samples_whisper = int(WHISPER_RATE * seconds)
            audio_f32 = np.interp(
                np.linspace(0, len(audio_f32), samples_whisper, endpoint=False),
                np.arange(len(audio_f32)), audio_f32
            ).astype(np.float32)
            
        return audio_f32
    except KeyboardInterrupt:
        raise
    except:
        return np.zeros(int(WHISPER_RATE * (seconds if seconds > 0 else 0.1)), dtype=np.float32)

def _is_silent(audio_np: np.ndarray) -> bool:
    """오디오 청크가 무음인지 판단"""
    rms = np.abs(audio_np).mean()
    return rms < (SILENCE_THRESHOLD * 0.5)

def _contains_wake_word(text: str) -> bool:
    """텍스트에 호출어가 포함되어 있는지 확인"""
    text_lower = text.lower().strip()
    return any(w in text_lower for w in WAKE_WORDS)

# ------------------------------------------------
# 실행 인터페이스
# ------------------------------------------------
def run_realtime():
    """실시간 오디오 모니터링 및 텍스트 변환 테스트"""
    model = _load_model()
    pa = _get_pyaudio_instance()
    stream = _open_stream(pa)
    
    UNIT_SEC = 0.5 
    audio_buffer = []
    is_speaking = False
    silence_count = 0 
    MAX_SILENCE_UNITS = int(SILENCE_TIMEOUT / UNIT_SEC)

    print(f"\n[STT] 오디오 모니터링 중... (종료: Ctrl+C)")
    print("-" * 50)

    try:
        _record_chunk(stream, 0.1, drain=True) 
        while True:
            chunk = _record_chunk(stream, UNIT_SEC)
            rms = np.sqrt(np.mean(chunk**2))
            
            if rms >= SILENCE_THRESHOLD:
                if not is_speaking:
                    is_speaking = True
                    print(f"\n[VAD] 음성 기반 활동 감지됨...        ", end="\r")
                    audio_buffer = []
                
                audio_buffer.append(chunk)
                silence_count = 0
            else:
                if is_speaking:
                    silence_count += 1
                    audio_buffer.append(chunk)
                    
                    if silence_count >= MAX_SILENCE_UNITS:
                        full_audio = np.concatenate(audio_buffer)
                        print(f"[STT] 처리 중...               ", end="\r")
                        result = _transcribe(model, full_audio)
                        
                        if result and len(result) > 1:
                            print(f"\n[텍스트] {result}")
                        
                        audio_buffer = []
                        is_speaking = False
                        silence_count = 0
                        print(f"\n[STT] 듣고 있습니다...              ", end="\r")
    except KeyboardInterrupt:
        print("\n\n[STT] 중단 요청됨.")
    finally:
        stream.stop_stream(); stream.close(); pa.terminate()
        print("[STT] 종료되었습니다.")

def listen_once(model=None, pa=None, stream=None) -> str:
    """호출어 대기 후 한 문장 인식"""
    if model is None: model = _load_model()
    close_pa = False
    if pa is None: pa = _get_pyaudio_instance(); close_pa = True
    close_stream = False
    if stream is None: stream = _open_stream(pa); close_stream = True

    print("\n[STT] 호출어(\"세이버\")를 기다리는 중...")
    _record_chunk(stream, 0.1, drain=True)

    try:
        while True:
            audio = _record_chunk(stream, 2.0)
            text = _transcribe(model, audio)
            if _contains_wake_word(text):
                print(f"\n[VAD] 호출어가 감지되었습니다.")
                break

        print("[STT] 말씀해 주세요...")
        question_buffer = []
        is_active = False
        silence_count = 0
        
        while True:
            chunk = _record_chunk(stream, 0.5)
            rms = np.abs(chunk).mean()
            
            if rms >= (SILENCE_THRESHOLD * 0.5):
                is_active = True
                question_buffer.append(chunk)
                silence_count = 0
            else:
                if is_active:
                    question_buffer.append(chunk)
                    silence_count += 1
                    if silence_count >= int(SILENCE_TIMEOUT / 0.5): break
                else:
                    silence_count += 1
                    if silence_count > 20: return "" # 장시간 침묵 시 초기화

        full_audio = np.concatenate(question_buffer)
        question = _transcribe(model, full_audio)
    finally:
        if close_stream: stream.stop_stream(); stream.close()
        if close_pa: pa.terminate()

    if question: print(f"[STT] 인식 결과: \"{question}\"")
    return question

def run_stt_loop(on_question_callback=None):
    """지속적으로 호출어를 대기하고 콜백을 실행하는 루프"""
    model = _load_model()
    pa = _get_pyaudio_instance()
    stream = _open_stream(pa)
    print("[STT] 루프 시작됨\n")
    try:
        while True:
            question = listen_once(model=model, pa=pa, stream=stream)
            if question and on_question_callback:
                on_question_callback(question)
    except KeyboardInterrupt:
        print("\n[STT] 루프 중단됨.")
    finally:
        stream.stop_stream(); stream.close(); pa.terminate()

if __name__ == "__main__":
    run_realtime()
