import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import sys
import re
import queue
import threading
import time
import tempfile
import platform
import subprocess
import logging
import pygame
import pyttsx3
import config
from voice.melo_wrapper import MeloEngine

_LOGGER = logging.getLogger(__name__)

class TTSHelper:
    """
    TTSHelper: 다중 엔진 지원 지능형 음성 합성 모듈
    ======================================================================
    - [PYTTSX3]: 즉각적인 반응 속도 (SAPI5/espeak/say 기반, 오프라인 전용)
    - [PPASO]: 온디바이스 한국어 초경량 ONNX 음성 합성
    - [MELO]: 고품질 딥러닝 음성 (MeloTTS 기반, 가속기 권장)
    - 대기열(Queue) 방식을 통해 문장 단위의 실시간 발화 지원
    """
    def __init__(self, rate=None, volume=1.0):
        self._engine_type = getattr(config, 'TTS_ENGINE', 'PYTTSX3')
        self._rate = rate if rate else getattr(config, 'TTS_RATE', 190)
        self._volume = volume
        
        # 큐 및 스레드 설정
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._is_speaking = False
        self._lock = threading.Lock()
        
        # macOS 및 일반 프로세스/엔진 중단 추적용 변수
        self._active_process = None
        self._active_engine = None
        
        # 엔진별 초기화
        self._melo_engine = None
        self._sapi_engine = None
        self._ppaso_engine = None
        
        if self._engine_type == "MELO":
            self._melo_engine = MeloEngine()
            try: pygame.mixer.init()
            except: pass
        elif self._engine_type == "PPASO":
            try:
                from voice.ppaso_wrapper import PpasoEngine
                self._ppaso_engine = PpasoEngine()
            except Exception as e:
                _LOGGER.warning("[TTS] PpasoEngine 로드 실패: %s. PYTTSX3로 폴백합니다.", e)
                self._engine_type = "PYTTSX3"
            try: pygame.mixer.init()
            except: pass
        
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        
        # 임시 파일 저장소 (MeloTTS/PpasoTTS 전용)
        self._temp_dir = os.path.join(tempfile.gettempdir(), "edge_saver_tts")
        os.makedirs(self._temp_dir, exist_ok=True)
        
        print(f"[TTS] {self._engine_type} 엔진 준비 완료 (속도: {self._rate}).")

    def _worker(self):
        """백그라운드에서 큐를 처리하며 음성을 생성합니다."""
        item = None
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.2)
                if item is None: break
                
                text, lang, speed = item if len(item) == 3 else (*item, 1.0)
                text = self._sanitize_text(text, lang=lang)
                if not text:
                    self._queue.task_done()
                    item = None
                    continue
                
                self._is_speaking = True
                
                if self._engine_type == "PYTTSX3":
                    if platform.system() == "Darwin":
                        # macOS의 경우 pyttsx3의 백그라운드 스레드 미동기(말겹침) 및 중단 버그 예방을 위해 
                        # OS 내장 say 명령어를 동기형 서브프로세스로 실행합니다.
                        try:
                            voice_map = {
                                'ko': 'Yuna',
                                'en': 'Samantha',
                                'ja': 'Kyoko',
                                'zh': 'Tingting'
                            }
                            voice_name = voice_map.get(lang, 'Yuna')
                            current_rate = int(self._rate * speed) if isinstance(speed, (int, float)) and speed < 5.0 else int(speed)
                            
                            # 발화 속도가 rate 단위(WPM)이므로 say 명령어에도 전달
                            cmd = ['say', '-v', voice_name, '-r', str(current_rate), text]
                            
                            self._active_process = subprocess.Popen(cmd)
                            self._active_process.wait()
                        except Exception as mac_ex:
                            try:
                                cmd = ['say', '-r', str(current_rate), text]
                                self._active_process = subprocess.Popen(cmd)
                                self._active_process.wait()
                            except:
                                pass
                        finally:
                            self._active_process = None
                    else:
                        # [v17 - 일회용 엔진 전략] (Linux/Windows)
                        # 문구별로 엔진을 새로 생성하여 스레드 교착 및 상태 고착을 원천 봉쇄합니다.
                        try:
                            temp_engine = pyttsx3.init()
                            self._active_engine = temp_engine
                            
                            # 위험 수치에 따른 동적 속도 조절 반영
                            current_rate = int(self._rate * speed) if isinstance(speed, (int, float)) and speed < 5.0 else int(speed)
                            temp_engine.setProperty('rate', current_rate)
                            temp_engine.setProperty('volume', self._volume)
                            
                            temp_engine.say(text)
                            temp_engine.runAndWait()
                            
                            # [자원 해제] 명시적 중단 및 소멸
                            temp_engine.stop()
                        except Exception as sapi_ex:
                            pass
                        finally:
                            self._active_engine = None
                            try:
                                del temp_engine
                            except:
                                pass
                elif self._engine_type == "PPASO" and self._ppaso_engine:
                    # 2. 온디바이스 한국어 초경량 엔진 (Ppaso-TTS)
                    temp_file = os.path.join(self._temp_dir, f"ppaso_{int(time.time()*1000)}.wav")
                    if self._ppaso_engine.speak_to_file(text, temp_file, lang=lang, speed=speed):
                        try:
                            pygame.mixer.music.load(temp_file)
                            pygame.mixer.music.play()
                            while pygame.mixer.music.get_busy():
                                if self._stop_event.is_set():
                                    pygame.mixer.music.stop()
                                    break
                                time.sleep(0.05)
                            pygame.mixer.music.unload()
                            if os.path.exists(temp_file):
                                os.remove(temp_file)
                        except Exception:
                            _LOGGER.exception("[TTS] PPASO 오디오 재생 실패 (file=%s)", temp_file)
                            try:
                                pygame.mixer.music.stop()
                                pygame.mixer.music.unload()
                            except Exception:
                                pass
                    else:
                        _LOGGER.error("[TTS] PPASO 합성 실패 (text=%r)", text[:100])
                else:
                    # 3. 고품질 합성 엔진 (MeloTTS)
                    temp_file = os.path.join(self._temp_dir, f"melo_{int(time.time()*1000)}.wav")
                    if self._melo_engine.speak_to_file(text, temp_file, lang=lang, speed=speed):
                        try:
                            pygame.mixer.music.load(temp_file)
                            pygame.mixer.music.play()
                            while pygame.mixer.music.get_busy():
                                if self._stop_event.is_set():
                                    pygame.mixer.music.stop()
                                    break
                                time.sleep(0.05)
                            pygame.mixer.music.unload()
                            if os.path.exists(temp_file):
                                os.remove(temp_file)
                        except Exception:
                            _LOGGER.exception("[TTS] MELO 오디오 재생 실패 (file=%s)", temp_file)
                            try:
                                pygame.mixer.music.stop()
                                pygame.mixer.music.unload()
                            except Exception:
                                pass
                    else:
                        _LOGGER.error("[TTS] MELO 합성 실패 (text=%r)", text[:100])
                
                self._is_speaking = False
                self._queue.task_done()
                item = None
                
            except queue.Empty: continue
            except Exception as e:
                _LOGGER.exception("[TTS] 워커 처리 실패: %s", e)
                self._is_speaking = False
                if item is not None:
                    try:
                        self._queue.task_done()
                    except ValueError:
                        pass
                time.sleep(1)

    def _sanitize_text(self, text, lang='ko'):
        """음성 출력을 위해 불필요한 특수문자 및 마크다운 기호 제거 및 발음 최적화"""
        if not text: return ""

        # 긴급 화재 신고 번호: 119 -> '일일구' 로 발음하도록 최적화 (백십구 방지)
        if lang == 'ko':
            text = re.sub(
                r'(?<![0-9A-Za-z_.])(?<!\d,)119(?![0-9A-Za-z_]|\.\d)'
                r'(?!\s*(?:명|개|건|원|조|항|호|층|미터|킬로|센티|초|분|시간|도|퍼센트|%|℃|°|kg\b|cm\b|km\b|m\b))',
                '일일구', text)

        # PDF/매뉴얼 줄바꿈 정제: 문맥 단절 방지
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
        
        # 목록 번호 발음 최적화: "1." -> "1번", "2." -> "2번" (묵음/끊김 현상 방지)
        text = re.sub(r'(\d+)\.(?=\s|$)', r'\1번', text)
        
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

    def speak(self, text, lang='ko', speed=None):
        """텍스트를 큐에 추가하여 순차적으로 음성 출력. speed가 지정되지 않으면 객체 생성시의 기본값 사용."""
        if not text: return
        target_speed = speed if speed is not None else 1.0
        self._queue.put((text, lang, target_speed))

    def speak_async(self, text, lang='ko', speed=None):
        """비동기 방식으로 호환성 유지"""
        self.speak(text, lang, speed)

    def warmup(self):
        """음성 엔진 초기 지연 방지를 위한 모델 예열"""
        if self._engine_type == "MELO" and self._melo_engine:
            self._melo_engine.get_model('ko')
            self._melo_engine.get_model('en')
        elif self._engine_type == "PPASO" and self._ppaso_engine:
            pass  # Ppaso-TTS는 초기화 시점에 ONNX 모델이 메모리에 즉시 준비됩니다.
        elif self._engine_type == "PYTTSX3":
            self.speak_async(" ")

    def is_speaking(self):
        """현재 음성이 합성/재생 중이거나 대기열에 작업이 남아있는지 확인합니다."""
        return self._is_speaking or not self._queue.empty()

    def wait_until_idle(self, timeout=None, poll_interval=0.05):
        """대기열과 현재 합성이 모두 끝날 때까지 대기. timeout 초과면 False 반환."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._queue.mutex:
                pending = self._queue.unfinished_tasks
            if pending == 0 and not self._is_speaking:
                return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(poll_interval)

    def stop(self):
        """현재 진행 중인 재생을 즉시 멈추고 대기열을 비웁니다."""
        # 1. 대기열 비우기
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        
        # 2. 현재 재생 중인 서브프로세스나 엔진 중단
        try:
            if self._active_process:
                self._active_process.terminate()
                try:
                    self._active_process.wait(timeout=0.5)
                except:
                    pass
                self._active_process = None
        except:
            pass

        try:
            if self._engine_type == "PYTTSX3" and self._active_engine:
                acquired = self._lock.acquire(blocking=False)
                if acquired:
                    try:
                        self._active_engine.stop()
                    finally:
                        self._lock.release()
            elif pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
        except:
            pass
