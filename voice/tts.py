"""feature/RAG text normalization with cancellable, serialized local speech."""
import logging
import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import platform
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
import pygame
import config
from voice.ppaso_wrapper import PpasoEngine

_LOGGER = logging.getLogger(__name__)

class TTSHelper:
    def __init__(self, rate=None, volume=1.0):
        self._engine_type = config.TTS_ENGINE
        self._prefer_gemini = config.GEMINI_TTS_ENABLED
        self._gemini_failure_until = 0.0
        self._rate = rate or config.TTS_RATE
        self._volume = volume
        self._queue = queue.Queue(maxsize=32)
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._generation = 0
        self._is_speaking = False
        self._active_process = None
        self._ppaso_engine = self._melo_engine = None
        self.last_error = ""
        self._temp_dir = Path(tempfile.gettempdir()) / "edge_saver_tts"
        self._temp_dir.mkdir(exist_ok=True)
        if self._engine_type == "PPASO":
            self._ppaso_engine = PpasoEngine()
            if not self._ppaso_engine.initialized:
                self.last_error = "PPASO unavailable; using PYTTSX3"
                _LOGGER.warning(self.last_error)
                self._engine_type = "PYTTSX3"
        elif self._engine_type == "MELO":
            from voice.melo_wrapper import MeloEngine
            self._melo_engine = MeloEngine()
        elif self._engine_type != "PYTTSX3":
            raise ValueError(f"Unknown TTS_ENGINE: {self._engine_type}")
        self._worker_thread = threading.Thread(target=self._worker, name="tts", daemon=True)
        self._worker_thread.start()
        print(f"[TTS] actual engine: {self._engine_type}")

    def _valid(self, generation):
        return not self._stop_event.is_set() and generation == self._generation

    @property
    def engine_type(self):
        with self._lock:
            return self._engine_type

    def set_engine(self, engine_type):
        """Switch engines without allowing cancelled work to use a new engine."""
        engine_type = engine_type.strip().upper()
        if engine_type not in {"AUTO", "PPASO", "PYTTSX3"}:
            raise ValueError("TTS engine must be AUTO, PPASO or PYTTSX3")
        if engine_type == "AUTO":
            with self._lock:
                if self._stop_event.is_set():
                    raise RuntimeError("TTS is closed")
                self.stop()
                self._prefer_gemini = config.GEMINI_TTS_ENABLED
                self._gemini_failure_until = 0.0
                return True
        # Prepare before cancelling playback so a failed switch preserves it.
        if engine_type == "PPASO" and self._ppaso_engine is None:
            engine = PpasoEngine()
            if not engine.initialized:
                raise RuntimeError("PPASO initialization failed")
            self._ppaso_engine = engine
        if engine_type == "PPASO" and not self._ppaso_engine.initialized:
            raise RuntimeError("PPASO unavailable")
        with self._lock:
            if self._stop_event.is_set():
                raise RuntimeError("TTS is closed")
            if self._engine_type == engine_type and not self._prefer_gemini:
                return False
            self.stop()
            self._engine_type = engine_type
            self._prefer_gemini = False
            self.last_error = ""
            return True

    def mode_command_response(self, query):
        parts = query.strip().split()
        if not parts or parts[0].lower() != "/tts":
            return None
        if len(parts) == 1:
            policy = "Gemini 답변은 Gemini TTS 우선" if self._prefer_gemini else "로컬 고정"
            return f"[TTS] {policy} / 로컬 엔진: {self.engine_type} | /tts auto | ppaso | pyttsx3"
        if len(parts) != 2 or parts[1].lower() not in {"auto", "ppaso", "pyttsx3"}:
            return "[TTS] 사용법: /tts | /tts auto | /tts ppaso | /tts pyttsx3"
        try:
            changed = self.set_engine(parts[1])
            mode = "Gemini 답변은 Gemini TTS 우선" if self._prefer_gemini else self.engine_type
            return f"[TTS] {'엔진 전환' if changed else '현재 엔진 유지'}: {mode}"
        except Exception as exc:
            return f"[TTS] 전환 실패: {exc} (현재 엔진: {self.engine_type})"

    def _play_file(self, path, generation):
        with self._lock:
            if not self._valid(generation):
                return
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play()
        while True:
            with self._lock:
                if not self._valid(generation) or not pygame.mixer.music.get_busy():
                    break
            time.sleep(0.03)
        with self._lock:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()

    def _system_speech(self, text, lang, speed, generation, output_path=None):
        rate = int(self._rate * speed)
        if platform.system() == "Darwin":
            voice = {"ko": "Yuna", "en": "Samantha", "ja": "Kyoko", "zh": "Tingting"}.get(lang, "Yuna")
            command = ["say", "-v", voice, "-r", str(rate), text]
        else:
            command = [sys.executable, str(Path(__file__).with_name("tts_worker.py")), text, lang, str(rate), str(self._volume)]
            if output_path is not None:
                command.extend(["--output", str(output_path)])
        with self._lock:
            if not self._valid(generation):
                return
            process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)
            self._active_process = process
        process.wait()
        with self._lock:
            if self._active_process is process:
                self._active_process = None
            if self._valid(generation) and process.returncode:
                raise RuntimeError(f"System TTS exited with {process.returncode}")

    def _worker(self):
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            path = None
            try:
                text, lang, speed, generation, provider = item
                with self._lock:
                    if not self._valid(generation):
                        continue
                    self._is_speaking = True
                    self.last_error = ""
                    engine_type = self._engine_type
                    local_engine = self._ppaso_engine if engine_type == "PPASO" else self._melo_engine
                    use_gemini = self._prefer_gemini and provider == "gemini"
                text = self._sanitize_text(text, lang)
                if not text:
                    continue
                if use_gemini and config.GEMINI_API_KEY and time.monotonic() >= self._gemini_failure_until:
                    path = self._temp_dir / f"speech_{uuid.uuid4().hex}.wav"
                    try:
                        from voice.gemini_tts import synthesize_to_file
                        synthesize_to_file(text, path)
                    except Exception as exc:
                        self._gemini_failure_until = time.monotonic() + config.GEMINI_TTS_RETRY_COOLDOWN
                        # Do not expose HTTP bodies, credentials, or answer text.
                        reason = str(exc) if isinstance(exc, RuntimeError) and str(exc).startswith("Gemini TTS HTTP ") else type(exc).__name__
                        _LOGGER.warning("Gemini TTS 실패 (%s), %s로 전환", reason, engine_type)
                    else:
                        if self._valid(generation):
                            print("[TTS] 재생 엔진: GEMINI", flush=True)
                            self._play_file(path, generation)
                        continue
                    if not self._valid(generation):
                        continue
                print(f"[TTS] 재생 엔진: {engine_type}", flush=True)
                if engine_type == "PYTTSX3" or (engine_type == "PPASO" and lang != "ko"):
                    if platform.system() == "Linux":
                        # eSpeak's direct playback uses aplay/ALSA, bypassing
                        # the SDL driver selected for remote desktop audio.
                        path = self._temp_dir / f"speech_{uuid.uuid4().hex}.wav"
                        self._system_speech(text, lang, speed, generation, output_path=path)
                        self._play_file(path, generation)
                    else:
                        self._system_speech(text, lang, speed, generation)
                else:
                    path = self._temp_dir / f"speech_{uuid.uuid4().hex}.wav"
                    if not local_engine.speak_to_file(text, str(path), lang=lang, speed=speed):
                        raise RuntimeError("Local speech synthesis failed")
                    self._play_file(path, generation)
            except Exception as exc:
                self.last_error = str(exc)
                _LOGGER.exception("TTS failed")
            finally:
                if path and path.exists():
                    path.unlink()
                self._is_speaking = False
                self._queue.task_done()

    def _sanitize_text(self, text, lang='ko'):
        """음성 출력을 위해 불필요한 특수문자 및 마크다운 기호 제거 및 발음 최적화"""
        if not text: return ""

        # Emergency numbers are digit names, not a cardinal quantity. Preserve
        # quantities, decimal numbers, larger numbers and identifiers.
        if lang == 'ko':
            text = re.sub(
                r'(?<![0-9A-Za-z_.])(?<!\d,)119(?![0-9A-Za-z_]|\.\d)'
                r'(?!\s*(?:명|개|건|원|조|항|호|층|미터|킬로|센티|초|분|시간|도|퍼센트|%|℃|°|kg\b|cm\b|km\b|m\b))',
                '일일구', text)

        # PDF의 짧은 제목/항목은 줄 경계를 잃으면 다음 단어와 붙어 들린다.
        # 긴 줄의 줄바꿈은 문장 중간의 자동 줄바꿈일 수 있어 공백으로만 잇는다.
        text = re.sub(r'(?im)^\s*[-–—]*\s*PAGE BREAK\s*[-–—]*\s*$', '', text)
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        joined = []
        previous = ""
        blank_line = False
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                blank_line = True
                continue
            if joined:
                end_of_phrase = blank_line or (len(previous) <= 20 and not re.search(r'[.!?。]$', previous))
                joined.append('. ' if end_of_phrase else ' ')
            joined.append(line)
            previous = line
            blank_line = False
        text = ''.join(joined)
        
        # [품질 향상] 목록 번호 발음 최적화: "1." -> "1번", "2." -> "2번"
        # 묵음 현상을 방지하고 더 자연스러운 안내를 제공합니다.
        text = re.sub(r'(\d+)\.(?!\d)\b', r'\1번', text)
        
        # 1. 마크다운 강조 기호(*) 및 기타 기호 제거
        text = text.replace('*', '')
        text = text.replace('#', ' ')
        
        # 2. 콜론(:) 및 대시(-) 처리 (자연스러운 쉼표나 공백으로 치환)
        text = text.replace(':', ', ')
        text = text.replace('-', ' ')
        
        # 3. 기타 마크다운 특수 기호 제거
        text = re.sub(r'[\|_`>]', ' ', text)
        
        # 4. 허용되지 않은 나머지 특수문자 제거 (이모지 등)
        text = re.sub(r'[^\w\s\d.,?!\(\)\[\]]', ' ', text)
        
        # 5. 연속된 공백을 하나로 압축하고 양끝 공백 제거
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def speak(self, text, lang="ko", speed=None, provider=None):
        if not text:
            return
        with self._lock:
            if self._stop_event.is_set():
                return
            self._queue.put_nowait((text, lang, speed or 1.0, self._generation, provider))

    def speak_async(self, text, lang="ko", speed=None, provider=None):
        self.speak(text, lang, speed, provider=provider)

    def warmup(self):
        # Model initialization occurs in __init__; no audible startup phrase.
        pass

    def is_speaking(self):
        return self._is_speaking or self._queue.unfinished_tasks > 0

    def wait_until_idle(self, timeout=None, poll_interval=0.05):
        deadline = None if timeout is None else time.monotonic()+timeout
        while self.is_speaking():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(poll_interval)
        return True

    def stop(self):
        with self._lock:
            self._generation += 1
            while True:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break
            if self._active_process and self._active_process.poll() is None:
                self._active_process.terminate()
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()

    def close(self):
        self._stop_event.set()
        self.stop()
        self._worker_thread.join(timeout=2)
