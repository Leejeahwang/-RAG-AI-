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

# Windows에서 심볼릭 링크 권한 에러(WinError 1314) 방지
if platform.system() == "Windows":
    os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
import io
import wave
import base64
# import ollama  # Gemma STT 미사용으로 주석 처리
import config

# ------------------------------------------------
# 시스템 설정 (config.py 연동)
# ------------------------------------------------
IS_WINDOWS = platform.system() == "Windows"
MACHINE = platform.machine().lower()
IS_PI = "arm" in MACHINE or "aarch64" in MACHINE

# Whisper 전용 설정
MODEL_SIZE  = config.STT_WHISPER_MODEL
DEVICE_TYPE = "cpu"       # 실행 장치 (cpu 또는 cuda)
COMPUTE     = "int8"      # 연산 정밀도

# 오디오 사양
SAMPLE_RATE  = 44100      # 기본 샘플링 레이트 (X-PRO 등은 44100 우선)
WHISPER_RATE = 16000      # 모델용 샘플링 레이트 (16kHz 표준)
CHUNK_SEC    = 0.5        # 처리 단위 (초)

STREAM_CHANNELS = 1
STREAM_FORMAT   = pyaudio.paInt16
STREAM_DEVICE   = None

SILENCE_THRESHOLD = 0.001  # 감도 극대화 (0.005 -> 0.001)
WAKE_WORDS      = ["세이버", "에이버", "세이 버", "세이바", "saver"] # 호출어
SILENCE_TIMEOUT = 1.8     # 무음 종료 대기 시간 (약간 늘림)

# ------------------------------------------------
# 장치 및 스트림 관리
# ------------------------------------------------
def _get_pyaudio_instance():
    return pyaudio.PyAudio()

def _find_best_device(pa: pyaudio.PyAudio):
    """플랫폼(Win/Linux)에 따른 최적화된 마이크 장치 검색"""
    # 환경 변수를 통해 수동 인덱스가 지정된 경우 최우선 사용
    manual_index = os.getenv("EDGE_SAVER_MIC_ID")
    if manual_index is not None:
        try:
            m_idx = int(manual_index)
            info = pa.get_device_info_by_index(m_idx)
            # print(f"[STT] 수동 지정된 마이크 사용: {info['name']} (인덱스 {m_idx})")
            return m_idx, int(info['maxInputChannels'])
        except:
            print(f"[STT] 경고: 수동 지정된 마이크 인덱스({manual_index})가 유효하지 않습니다.")

    all_inputs = []
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            all_inputs.append(info)

    # 블루투스 이어폰(Buds 등) 및 특정 하드웨어 우선 검색
    # 전용 마이크(X-PRO)를 최우선으로, 이후 이어폰류 검색
    priority_keywords = ["X-PRO", "buds", "수화기"]
    for kw in priority_keywords:
        for info in all_inputs:
            if kw.lower() in info["name"].lower():
                # print(f"[STT] 우선순위 장치 선택됨: {info['name']} (인덱스 {info['index']})")
                return info['index'], int(info['maxInputChannels'])

    if IS_WINDOWS:
        keywords = ["배열", "intel", "microphone", "마이크"]
    else:
        keywords = ["usb", "capture", "audio", "default", "hw:"]

    for kw in keywords:
        for info in all_inputs:
            name = info["name"].lower()
            if kw in name and "stereo mix" not in name and "loopback" not in name:
                # print(f"[STT] 장치 선택됨: {info['name']} (인덱스 {info['index']})")
                return info['index'], int(info['maxInputChannels'])

    try:
        default_info = pa.get_default_input_device_info()
        # print(f"[STT] 기본 장치 사용: {default_info['name']}")
        return default_info['index'], int(default_info['maxInputChannels'])
    except:
        pass
            
    return 0, 1

def _open_stream(pa: pyaudio.PyAudio) -> pyaudio.Stream:
    global STREAM_CHANNELS, STREAM_FORMAT, STREAM_DEVICE, SAMPLE_RATE
    device_idx, max_channels = _find_best_device(pa)
    STREAM_DEVICE = device_idx
    
    # 44100Hz (X-PRO 등) 우선순위 상향
    rates_to_try = [44100, 48000, 16000, 8000]
    channels_to_try = [max_channels] if max_channels <= 2 else [2, 1]
    if 1 not in channels_to_try: channels_to_try.append(1)

    print(f"[STT] 오디오 스트림 초기화 중...")
    for rate in rates_to_try:
        for ch in channels_to_try:
            try:
                print(f"    [STT] {rate}Hz, {ch}ch 시도 중...", end="\r")
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
def _numpy_to_wav(audio_np: np.ndarray) -> bytes:
    """Numpy 오디오 데이터를 WAV 바이너리로 변환 (Ollama 전용)"""
    # -1.0 ~ 1.0 -> Int16 변환
    audio_int16 = (audio_np * 32767).astype(np.int16)
    
    with io.BytesIO() as wav_io:
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2) # 16-bit
            wav_file.setframerate(WHISPER_RATE)
            wav_file.writeframes(audio_int16.tobytes())
        return wav_io.getvalue()

def _load_model():
    """설정에 따라 STT 엔진 모델 로드 (Gemma 모드시 로드 스킵)"""
    if config.STT_ENGINE == "GEMMA":
        print(f"[STT] 'GEMMA' 통합 모드 사용 (Ollama: {config.STT_GEMMA_MODEL})")
        return None # Gemma는 API를 통해 로컬 Ollama 서버와 통신하므로 로컬 로드 불요
        
    print(f"[STT] 플랫폼: {platform.system()}")
    print(f"[STT] 'WHISPER' 백업 모드 가동 중 ({MODEL_SIZE})...", end=" ", flush=True)
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(MODEL_SIZE, device=DEVICE_TYPE, compute_type=COMPUTE)
        print("완료")
        return model
    except ImportError:
        print("실패 (라이브러리 없음)")
        return None

def _transcribe(model, audio_np: np.ndarray) -> tuple[str, str]:
    """설정된 엔진에 따라 오디오를 텍스트로 변환"""
    # 1. 소프트웨어 게인 증폭 (소리가 매우 작은 사용자 환경을 위해 15배 증폭)
    audio_np = audio_np * 15.0
    
    # 볼륨 정문화 (Normalization 및 클리핑 방지)
    max_val = np.abs(audio_np).max()
    if max_val > 0.01:
        audio_np = audio_np / max_val * 0.9

    """
    # [사용자 요청으로 주석 처리] 1. Gemma 4 네이티브 STT 모드
    if config.STT_ENGINE == "GEMMA":
        try:
            wav_bytes = _numpy_to_wav(audio_np)
            
            # [DEBUG] 실제로 보낸 소리를 파일로 저장하여 확인 (사용자용)
            with open("debug_stt.wav", "wb") as f:
                f.write(wav_bytes)

            response = ollama.chat(
                model=config.STT_GEMMA_MODEL,
                messages=[{
                    'role': 'user',
                    'content': 'Transcribe the provided audio to text accurately.',
                    'audio': [wav_bytes] 
                }]
            )
            text = response['message']['content'].strip()
            
            if "provide the audio" in text.lower() or not text:
                response = ollama.chat(
                    model=config.STT_GEMMA_MODEL,
                    messages=[{
                        'role': 'user',
                        'content': 'Transcribe the provided audio to text accurately.',
                        'images': [wav_bytes] 
                    }]
                )
                text = response['message']['content'].strip()

            print(f" [DEBUG Gemma STT] >> '{text}'")
            return text, "ko"
        except Exception as e:
            print(f"[STT] Gemma 인식 오류: {e}")
            return "", "ko"
    """

    # 2. Whisper 백업 모드
    if model is None: return "", "ko"
    
    segments, info = model.transcribe(
        audio_np, 
        language="ko", # 한국어로 강제 고정하여 인식률 향상
        beam_size=5,
        initial_prompt="아파트 화재, 대응방법, 소화기 사용법, 대피 요령, 비상벨, 소방 대피, 긴급 상황.",
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 700}, # 무음 감지 기준 상향하여 잘림 방지
        condition_on_previous_text=False, # 이전 문맥 무시하여 환각 방지
        temperature=0.0 # 무작위성 제거
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    
    if info.language_probability < 0.6:
        return "", "ko"
        
    return text, info.language

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
        
        # 스테레오 -> 모노 믹싱 (2채널 이상일 경우에만 합산)
        if STREAM_CHANNELS >= 2:
            try:
                audio_f32 = audio_f32.reshape(-1, STREAM_CHANNELS).mean(axis=1)
            except:
                # 리쉐이프 실패 시 첫 번째 채널이라도 사용
                audio_f32 = audio_f32[:len(audio_f32)//STREAM_CHANNELS]
        
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
            
            # [게이지 출력] 실시간 음량 시각화
            rms = np.sqrt(np.mean(chunk**2)) * 32768
            peak = np.abs(chunk).max() * 32768
            bar_len = int(min(rms / 500, 30))
            bar = "#" * bar_len + "-" * (30 - bar_len)
            print(f"[Mic Level: {bar}] Peak: {int(peak):<5}", end="\r")

            if np.abs(chunk).mean() >= SILENCE_THRESHOLD:
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
                        result, lang = _transcribe(model, full_audio)
                        
                        if result and len(result) > 1:
                            print(f"\n[텍스트] ({lang}) {result}")
                        
                        audio_buffer = []
                        is_speaking = False
                        silence_count = 0
                        print(f"\n[STT] 듣고 있습니다...              ", end="\r")
    except KeyboardInterrupt:
        print("\n\n[STT] 중단 요청됨.")
    finally:
        stream.stop_stream(); stream.close(); pa.terminate()
        print("[STT] 종료되었습니다.")

def listen_once(model=None, pa=None, stream=None, use_wake_word=True, allowed_langs=['ko', 'en', 'ja', 'zh']) -> str:
    """음성 인식 수행 (선택적으로 호출어 대기 가능 및 언어 필터링 지원)"""
    if model is None: model = _load_model()
    close_pa = False
    if pa is None: pa = _get_pyaudio_instance(); close_pa = True
    close_stream = False
    if stream is None: stream = _open_stream(pa); close_stream = True

    _record_chunk(stream, 0.1, drain=True)

    try:
        if use_wake_word:
            print("\n[STT] 호출어(\"세이버\")를 기다리는 중...")
            while True:
                audio = _record_chunk(stream, 2.0)
                text, lang = _transcribe(model, audio)
                if _contains_wake_word(text):
                    print(f"\n[VAD] 호출어가 감지되었습니다. (감지 언어: {lang})")
                    break

        print("[STT] 말씀해 주세요...")
        question_buffer = []
        is_active = False
        silence_count = 0
        
        pre_buffer = [] # 첫 단어 잘림 방지용 예비 버퍼
        while True:
            chunk = _record_chunk(stream, 0.2) # 0.5 -> 0.2로 세분화하여 반응성 향상
            
            rms_val = np.sqrt(np.mean(chunk**2)) * 32768
            peak_val = np.abs(chunk).max() * 32768
            bar_len = int(min(rms_val / 500, 30))
            bar = "#" * bar_len + "-" * (30 - bar_len)
            print(f"[Mic Level: {bar}] Peak: {int(peak_val):<5}", end="\r")

            rms = np.abs(chunk).mean()
            if rms >= (SILENCE_THRESHOLD * 0.4): # 민감도 살짝 상향
                if not is_active:
                    is_active = True
                    # 침묵 구간의 마지막 0.6초(3개 청크)를 합쳐서 첫 단어 복원
                    question_buffer.extend(pre_buffer[-3:]) 
                
                question_buffer.append(chunk)
                silence_count = 0
            else:
                if is_active:
                    question_buffer.append(chunk)
                    silence_count += 1
                    if silence_count >= int(SILENCE_TIMEOUT / 0.2): break
                else:
                    # 아직 말을 안 할 때는 예비 버퍼에 지속 저장 (최대 5개 유지)
                    pre_buffer.append(chunk)
                    if len(pre_buffer) > 5: pre_buffer.pop(0)
                    
                    silence_count += 1
                    if silence_count > 50: return "", "" 

        if not question_buffer:
            print(" " * 60, end="\r") # 게이지 지우기
            return "", ""

        print("\n[STT] 처리 중...               ") # 새 줄로 넘어가서 게이지 지우기
        full_audio = np.concatenate(question_buffer)
        question, lang = _transcribe(model, full_audio)
        
        # [환각 및 오판 방지 정책]
        # 1. 2글자 미만 무시
        # 2. 지정된 언어(allowed_langs)가 아니면 소음으로 간주
        if len(question.strip()) < 2 or (allowed_langs and lang not in allowed_langs):
            return "", "" # 무시하고 다시 대기

            
    finally:
        if close_stream: stream.stop_stream(); stream.close()
        if close_pa: pa.terminate()

    return question, lang

def run_stt_loop(on_question_callback=None):
    """지속적으로 호출어를 대기하고 콜백을 실행하는 루프"""
    model = _load_model()
    pa = _get_pyaudio_instance()
    stream = _open_stream(pa)
    print("[STT] 루프 시작됨\n")
    try:
        while True:
            question, lang = listen_once(model=model, pa=pa, stream=stream)
            if question and on_question_callback:
                on_question_callback(question, lang)
    except KeyboardInterrupt:
        print("\n[STT] 루프 중단됨.")
    finally:
        stream.stop_stream(); stream.close(); pa.terminate()

if __name__ == "__main__":
    run_realtime()
