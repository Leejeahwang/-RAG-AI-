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
import shutil
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
import pygame
import config
from voice.ppaso_wrapper import PpasoEngine
from voice.pronunciation import preserve_spoken_notation, local_pronunciation

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Replay:
    group: int
    generation: int


class TTSHelper:
    def __init__(self, rate=None, volume=1.0):
        self._engine_type = config.TTS_ENGINE
        self._prefer_gemini = config.GEMINI_TTS_ENABLED
        self._gemini_failure_until = 0.0
        self._gemini_last_error = ""
        self._rate = rate or config.TTS_RATE
        self._volume = volume
        self._queue = queue.Queue(maxsize=32)
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._generation = 0
        self._yield_requested = threading.Event()
        self._yield_ready = threading.Event()
        self._is_speaking = False
        self._active_process = None
        self._ppaso_engine = self._melo_engine = None
        self.last_error = ""
        self._temp_dir = Path(tempfile.gettempdir()) / "edge_saver_tts"
        self._temp_dir.mkdir(exist_ok=True)
        self._audio_cache_dir = tempfile.TemporaryDirectory(prefix='event_audio_', dir=self._temp_dir)
        self._audio_cache = {}
        self._audio_callbacks = {}
        self._cache_sources = {}
        self._cache_upgrades = {}
        self._cache_retry_after = 0.0
        self._audio_group = None
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
        self._cache_retry_thread = threading.Thread(target=self._retry_cached_audio,
                                                     name='tts-cache-retry', daemon=True)
        self._cache_retry_thread.start()
        print(f"[TTS] 로컬 엔진: {self._engine_type} | Gemini TTS 우선: {'켜짐' if self._prefer_gemini else '꺼짐'}")

    def _valid(self, generation):
        return not self._stop_event.is_set() and generation == self._generation

    @property
    def engine_type(self):
        with self._lock:
            return self._engine_type

    def set_engine(self, engine_type):
        """Switch engines without allowing cancelled work to use a new engine."""
        engine_type = engine_type.strip().upper()
        if engine_type not in {"AUTO", "GEMINI", "PPASO", "PYTTSX3"}:
            raise ValueError("TTS engine must be AUTO, GEMINI, PPASO or PYTTSX3")
        if engine_type in {"AUTO", "GEMINI"}:
            if engine_type == "GEMINI" and not config.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY가 필요합니다")
            with self._lock:
                if self._stop_event.is_set():
                    raise RuntimeError("TTS is closed")
                self.stop()
                self._prefer_gemini = engine_type == "GEMINI" or config.GEMINI_TTS_ENABLED
                self._gemini_failure_until = 0.0
                self._gemini_last_error = ""
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
            policy = "Gemini 답변·첫 비상 안내·구역 안내는 Gemini TTS 우선" if self._prefer_gemini else "로컬 고정"
            detail = f" / 최근 Gemini 실패: {self._gemini_last_error}" if self._gemini_last_error else ""
            return f"[TTS] {policy} / 로컬 엔진: {self.engine_type}{detail} | /tts auto | gemini | ppaso | pyttsx3"
        if len(parts) != 2 or parts[1].lower() not in {"auto", "gemini", "ppaso", "pyttsx3"}:
            return "[TTS] 사용법: /tts | /tts auto | /tts gemini | /tts ppaso | /tts pyttsx3"
        try:
            changed = self.set_engine(parts[1])
            mode = "Gemini 답변·첫 비상 안내·구역 안내는 Gemini TTS 우선" if self._prefer_gemini else self.engine_type
            return f"[TTS] {'엔진 전환' if changed else '현재 엔진 유지'}: {mode}"
        except Exception as exc:
            return f"[TTS] 전환 실패: {exc} (현재 엔진: {self.engine_type})"

    def _play_file(self, path, generation, on_ready=None):
        # Only inspect local PCM data; never infer word boundaries by cutting
        # at an arbitrary playback duration. Unsupported files yield at EOF.
        pauses = None
        self._wait_for_update(generation)
        with self._lock:
            if not self._valid(generation):
                return False
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play()
            if not pygame.mixer.music.get_busy():
                raise RuntimeError('Audio playback did not start')
            if on_ready:
                on_ready()
        while True:
            with self._lock:
                if not self._valid(generation) or not pygame.mixer.music.get_busy():
                    break
                position = pygame.mixer.music.get_pos() / 1000
            if self._yield_requested.is_set():
                if pauses is None:
                    pauses = self._speech_pauses(path)
                # Scanning can take time on a Pi. Re-read the position and
                # only pause while still inside a quiet interval, never after
                # a previously selected pause has already passed.
                with self._lock:
                    position = pygame.mixer.music.get_pos() / 1000
                if any(start <= position < end for start, end in pauses):
                    with self._lock:
                        if self._valid(generation):
                            pygame.mixer.music.pause()
                    self._wait_for_update(generation)
                    with self._lock:
                        if self._valid(generation):
                            pygame.mixer.music.unpause()
            time.sleep(0.03)
        with self._lock:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        self._wait_for_update(generation)
        return self._valid(generation)

    @staticmethod
    def _speech_pauses(path):
        """Return interiors of >=200 ms quiet gaps of signed 16-bit PCM."""
        points = []
        try:
            with wave.open(str(path), 'rb') as audio:
                if audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
                    return points
                rate, channels = audio.getframerate(), audio.getnchannels()
                window = max(1, int(rate * .04))
                frames = 0
                quiet_start = None
                voiced = False
                while data := audio.readframes(window):
                    samples = array('h', data)
                    if sys.byteorder != 'little':
                        samples.byteswap()
                    count = len(samples) // channels
                    if max(map(abs, samples), default=0) <= 160:
                        if quiet_start is None:
                            quiet_start = frames
                    else:
                        if voiced and quiet_start is not None and frames - quiet_start >= rate * .2:
                            points.append((quiet_start / rate + .04, frames / rate - .04))
                        quiet_start = None
                        voiced = True
                    frames += count
                if voiced and quiet_start is not None and frames - quiet_start >= rate * .2:
                    points.append((quiet_start / rate + .04, frames / rate - .04))
        except (OSError, EOFError, wave.Error):
            pass
        return points

    def request_boundary(self):
        """Pause at the next speech gap, or before the next prepared clip."""
        self._yield_requested.set()

    def boundary_ready(self):
        return self._yield_ready.is_set() or not self.is_speaking()

    def cancel_boundary(self):
        self._yield_requested.clear()
        self._yield_ready.clear()

    def _wait_for_update(self, generation):
        while self._yield_requested.is_set() and self._valid(generation):
            self._yield_ready.set()
            self._stop_event.wait(.02)

    def _play_with_retry(self, path, generation, on_ready=None):
        notified = False
        def started():
            nonlocal notified
            if not notified and on_ready:
                on_ready()
            notified = True
        for attempt in range(2):
            if not self._valid(generation):
                return False
            try:
                result = self._play_prepared(path, generation, started if on_ready else None)
                if result is False or not self._valid(generation):
                    return False
                self.last_error = ''
                return True
            except Exception as exc:
                if not self._valid(generation):
                    return False
                self.last_error = type(exc).__name__
                if attempt:
                    print('[TTS] 재생 실패: 출력 장치를 확인하십시오. 해당 안내를 재생하지 못했습니다.', flush=True)
                    raise
                _LOGGER.warning('TTS 재생 실패 (%s); 음성 스트림을 다시 열어 한 번 재시도합니다', type(exc).__name__)
                with self._lock:
                    if self._valid(generation):
                        # Siren channels share the mixer. A global quit would
                        # silence the warning before speech has recovered.
                        try:
                            pygame.mixer.music.stop()
                            pygame.mixer.music.unload()
                        except pygame.error:
                            pass
                if self._stop_event.wait(.15):
                    return False

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
                if isinstance(item, _Replay):
                    with self._lock:
                        if not self._valid(item.generation) or item.group != self._audio_group:
                            continue
                        self._is_speaking = True
                        self.last_error = ''
                        self._apply_cache_upgrades()
                        clips = [self._audio_cache[key] for key in ('first', 'zone', 'rules')
                                 if key in self._audio_cache]
                    for cached_path, engine in clips:
                        if not self._valid(item.generation):
                            break
                        print(f'[TTS] 저장 음성 재생: {engine}', flush=True)
                        callback = self._audio_callbacks.get(str(cached_path))
                        self._play_with_retry(cached_path, item.generation, callback)
                    continue
                text, lang, speed, generation, provider, on_ready, cache_key = item
                with self._lock:
                    if not self._valid(generation):
                        continue
                    self._is_speaking = True
                    self.last_error = ""
                    engine_type = self._engine_type
                    local_engine = self._ppaso_engine if engine_type == "PPASO" else self._melo_engine
                    use_gemini = self._prefer_gemini and provider in {"gemini", "emergency", "zone"}
                source_text = text
                text = self._sanitize_text(text, lang)
                retry_text = text if use_gemini else None
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
                        self._gemini_last_error = reason
                        _LOGGER.warning("Gemini TTS 실패 (%s), %s로 전환", reason, engine_type)
                    else:
                        self._gemini_last_error = ""
                        if self._valid(generation):
                            print("[TTS] 재생 엔진: GEMINI", flush=True)
                            self._play_and_cache(path, generation, on_ready, cache_key, 'GEMINI')
                        continue
                    if not self._valid(generation):
                        continue
                print(f"[TTS] 재생 엔진: {engine_type}", flush=True)
                if engine_type in {'PPASO', 'PYTTSX3'}:
                    # Retain raw slashes/hyphens for reviewed terms such as
                    # E/V and E-STOP; Gemini receives only common cleanup.
                    text = self._sanitize_text(local_pronunciation(source_text, lang), lang)
                if engine_type == "PYTTSX3" or (engine_type == "PPASO" and lang != "ko"):
                    if platform.system() == "Linux" or ((on_ready or cache_key) and platform.system() == "Windows"):
                        # eSpeak's direct playback uses aplay/ALSA, bypassing
                        # the SDL driver selected for remote desktop audio.
                        path = self._temp_dir / f"speech_{uuid.uuid4().hex}.wav"
                        self._system_speech(text, lang, speed, generation, output_path=path)
                        self._play_and_cache(path, generation, on_ready, cache_key, engine_type, retry_text)
                    else:
                        with self._lock:
                            if not self._valid(generation):
                                continue
                            if on_ready:
                                on_ready()
                        self._system_speech(text, lang, speed, generation)
                else:
                    path = self._temp_dir / f"speech_{uuid.uuid4().hex}.wav"
                    if not local_engine.speak_to_file(text, str(path), lang=lang, speed=speed):
                        raise RuntimeError("Local speech synthesis failed")
                    self._play_and_cache(path, generation, on_ready, cache_key, engine_type, retry_text)
            except Exception as exc:
                self.last_error = str(exc)
                _LOGGER.exception("TTS failed")
            finally:
                if path and path.exists():
                    path.unlink()
                self._is_speaking = False
                self._queue.task_done()

    def _play_prepared(self, path, generation, on_ready):
        if on_ready is None:
            return self._play_file(path, generation)
        else:
            return self._play_file(path, generation, on_ready=on_ready)

    def _play_and_cache(self, path, generation, on_ready, cache_key, engine, retry_text=None):
        if cache_key is None:
            self._play_with_retry(path, generation, on_ready)
            return
        group, part = cache_key
        with self._lock:
            if not self._valid(generation) or group != self._audio_group:
                return
            target = Path(self._audio_cache_dir.name) / f'{uuid.uuid4().hex}.wav'
            shutil.copyfile(path, target)
            previous = self._audio_cache.get(part)
            self._audio_cache[part] = (target, engine)
            self._cache_sources.pop(part, None)
            if retry_text and engine != 'GEMINI':
                self._cache_sources[part] = (retry_text, target)
            if on_ready:
                self._audio_callbacks[str(target)] = on_ready
            if previous:
                self._audio_callbacks.pop(str(previous[0]), None)
                previous[0].unlink(missing_ok=True)
        # Keep successfully synthesized speech even when the output device is
        # temporarily unavailable, so the regular repeat can retry it later.
        self._play_with_retry(path, generation, on_ready)

    def _retry_cached_audio(self):
        """Prepare one replacement per cooldown without blocking playback."""
        while not self._stop_event.wait(.2):
            self._retry_cached_audio_once()

    def _retry_cached_audio_once(self):
        with self._lock:
            now = time.monotonic()
            if (self._stop_event.is_set() or not self._prefer_gemini
                    or config.AI_PROVIDER == 'local'
                    or not config.GEMINI_API_KEY or self._audio_group is None
                    or now < max(self._gemini_failure_until, self._cache_retry_after)):
                return False
            pending = next(((part, self._cache_sources[part])
                            for part in ('first', 'zone', 'rules')
                            if part in self._cache_sources and part not in self._cache_upgrades), None)
            if pending is None:
                return False
            part, (text, original) = pending
            group, generation = self._audio_group, self._generation
            # Rate-limit successful upgrades too, instead of sending all
            # fallback clips immediately after a quota failure.
            self._cache_retry_after = now + max(1.0, config.GEMINI_TTS_RETRY_COOLDOWN)
        path = self._temp_dir / f'upgrade_{uuid.uuid4().hex}.wav'
        try:
            from voice.gemini_tts import synthesize_to_file
            synthesize_to_file(text, path)
            with self._lock:
                if (not self._valid(generation) or not self._prefer_gemini
                        or config.AI_PROVIDER == 'local'
                        or group != self._audio_group
                        or self._cache_sources.get(part) != (text, original)
                        or self._audio_cache.get(part, (None,))[0] != original):
                    return False
                self._cache_upgrades[part] = (path, original, generation)
                self._gemini_last_error = ''
                print(f'[TTS] Gemini 저장 음성 준비 완료: {part} (다음 반복부터 적용)', flush=True)
                path = None
                return True
        except Exception as exc:
            with self._lock:
                if self._valid(generation) and group == self._audio_group:
                    self._gemini_failure_until = time.monotonic() + max(1.0, config.GEMINI_TTS_RETRY_COOLDOWN)
                    reason = str(exc) if isinstance(exc, RuntimeError) and str(exc).startswith('Gemini TTS HTTP ') else type(exc).__name__
                    self._gemini_last_error = reason
                    _LOGGER.warning('Gemini 저장 음성 재시도 실패 (%s); 기존 음성을 유지합니다', reason)
            return False
        finally:
            if path is not None:
                path.unlink(missing_ok=True)

    def _apply_cache_upgrades(self):
        """Called by the playback worker, before taking its replay snapshot."""
        for part, (prepared, original, generation) in list(self._cache_upgrades.items()):
            if (self._valid(generation) and self._prefer_gemini
                    and config.AI_PROVIDER != 'local'
                    and self._audio_cache.get(part, (None,))[0] == original):
                target = Path(self._audio_cache_dir.name) / f'{uuid.uuid4().hex}.wav'
                try:
                    shutil.copyfile(prepared, target)
                except OSError:
                    target.unlink(missing_ok=True)
                    prepared.unlink(missing_ok=True)
                    del self._cache_upgrades[part]
                    _LOGGER.warning('Gemini 저장 음성 교체 실패; 기존 음성을 유지합니다')
                    continue
                self._audio_cache[part] = (target, 'GEMINI')
                callback = self._audio_callbacks.pop(str(original), None)
                if callback:
                    self._audio_callbacks[str(target)] = callback
                self._cache_sources.pop(part, None)
                original.unlink(missing_ok=True)
                print(f'[TTS] 저장 음성 교체: {part} → GEMINI', flush=True)
            prepared.unlink(missing_ok=True)
            del self._cache_upgrades[part]

    def begin_event_audio(self, group):
        """Called after stop(); keep only this incident's completed speech files."""
        with self._lock:
            self.clear_event_audio(self._audio_group)
            self._audio_group = group

    def clear_event_audio(self, group):
        with self._lock:
            if group != self._audio_group:
                return
            for path, _ in self._audio_cache.values():
                path.unlink(missing_ok=True)
            self._audio_cache.clear()
            self._audio_callbacks.clear()
            self._cache_sources.clear()
            for prepared, _, _ in self._cache_upgrades.values():
                prepared.unlink(missing_ok=True)
            self._cache_upgrades.clear()
            self._audio_group = None

    def replay_event_audio(self, group):
        """Replay prepared files; background upgrades never block this queue."""
        with self._lock:
            if self._stop_event.is_set() or group != self._audio_group or not self._audio_cache:
                return False
            self._queue.put_nowait(_Replay(group, self._generation))
            return True

    def _sanitize_text(self, text, lang='ko'):
        """음성 출력을 위해 불필요한 특수문자 및 마크다운 기호 제거 및 발음 최적화"""
        if not text: return ""

        text = preserve_spoken_notation(text, lang)

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

    def speak(self, text, lang="ko", speed=None, provider=None, on_ready=None, cache_key=None):
        if not text:
            return
        with self._lock:
            if self._stop_event.is_set():
                return
            self._queue.put_nowait((text, lang, speed or 1.0, self._generation, provider, on_ready, cache_key))

    def speak_async(self, text, lang="ko", speed=None, provider=None, on_ready=None, cache_key=None):
        self.speak(text, lang, speed, provider=provider, on_ready=on_ready, cache_key=cache_key)

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
            self.cancel_boundary()
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
        self._cache_retry_thread.join(timeout=2)
        with self._lock:
            self.clear_event_audio(self._audio_group)
            self._audio_cache_dir.cleanup()
