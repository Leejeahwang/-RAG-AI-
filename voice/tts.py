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
from voice.ppaso_wrapper import PpasoEngine

_LOGGER = logging.getLogger(__name__)

class TTSHelper:
    """
    TTSHelper: 다중 엔진 지원 지능형 음성 합성 모듈
    ======================================================================
    - [PYTTSX3]: 즉각적인 반응 속도 (SAPI5 기반, 오프라인 전용)
    - [MELO]: 고품질 딥러닝 음성 (MeloTTS 기반, 가속기 권장)
    - [PPASO]: 초경량 21MB 온디바이스 음성 (Ppaso-TTS 기반, NPU/CPU 친화)
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
        self._lock = threading.Lock() # SAPI5(pyttsx3) 멀티스레딩 동시 경합 크래시 원천 차단용 전역 락
        
        # macOS 및 일반 프로세스/엔진 중단 추적용 변수
        self._active_process = None
        self._active_engine = None
        
        # 엔진별 초기화
        self._melo_engine = None
        self._ppaso_engine = None
        self._sapi_engine = None
        
        if self._engine_type == "MELO":
            # Melo 래퍼는 import 시 Windows MeCab 모듈을 교체하므로,
            # PPASO가 사용하는 실제 G2P/MeCab import에 영향을 주지 않도록 필요할 때만 로드한다.
            from voice.melo_wrapper import MeloEngine
            self._melo_engine = MeloEngine()
            try: pygame.mixer.init()
            except Exception:
                _LOGGER.exception("[TTS] pygame mixer 초기화 실패")
        elif self._engine_type == "PPASO":
            self._ppaso_engine = PpasoEngine()
            try: pygame.mixer.init()
            except Exception:
                _LOGGER.exception("[TTS] pygame mixer 초기화 실패")
        
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        
        # 임시 파일 저장소 (MeloTTS 전용)
        self._temp_dir = os.path.join(tempfile.gettempdir(), "edge_saver_tts")
        os.makedirs(self._temp_dir, exist_ok=True)
        
        print(f"[TTS] {self._engine_type} 엔진 준비 완료 (속도: {self._rate}).")

    def _worker(self):
        """백그라운드에서 큐를 처리하며 음성을 생성합니다."""
        while not self._stop_event.is_set():
            item = None
            try:
                item = self._queue.get(timeout=0.2)
                if item is None:
                    self._queue.task_done()
                    break
                
                text, lang, speed = item if len(item) == 3 else (*item, 1.0)
                text = self._sanitize_text(text, lang=lang)
                if not text:
                    self._queue.task_done()
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
                            current_rate = int(self._rate * speed) if isinstance(speed, (int, float)) and speed < 3.0 else self._rate
                            
                            # 발화 속도가 rate 단위(WPM)이므로 say 명령어에도 전달
                            cmd = ['say', '-v', voice_name, '-r', str(current_rate), text]
                            
                            self._active_process = subprocess.Popen(cmd)
                            self._active_process.wait()
                        except Exception as mac_ex:
                            _LOGGER.warning("[TTS] macOS 지정 음성 재생 실패, 기본 음성으로 재시도: %s", mac_ex)
                            # 만약 특정 목소리가 없거나 에러 시 기본 목소리로 폴백
                            try:
                                cmd = ['say', '-r', str(current_rate), text]
                                self._active_process = subprocess.Popen(cmd)
                                self._active_process.wait()
                            except Exception:
                                _LOGGER.exception("[TTS] macOS 기본 음성 재생도 실패")
                        finally:
                            self._active_process = None
                    else:
                        # [v17 - 일회용 엔진 전략] (Windows/Linux)
                        # 문구별로 엔진을 새로 생성하여 스레드 교착 및 상태 고착을 원천 봉쇄합니다.
                        # 멀티스레드 동시 난입으로 인한 pyttsx3 C++ COM 객체 세그멘테이션 오류를 방지하기 위해 락(Lock) 획득
                        with self._lock:
                            try:
                                temp_engine = pyttsx3.init()
                                self._active_engine = temp_engine
                                
                                # 위험 수치에 따른 동적 속도 조절 반영
                                current_rate = int(self._rate * speed) if isinstance(speed, (int, float)) and speed < 3.0 else self._rate
                                temp_engine.setProperty('rate', current_rate)
                                temp_engine.setProperty('volume', self._volume)
                                
                                temp_engine.say(text)
                                temp_engine.runAndWait()
                                
                                # [자원 해제] 명시적 중단 및 소멸
                                temp_engine.stop()
                            except Exception as sapi_ex:
                                _LOGGER.exception("[TTS] PYTTSX3 발화 실패: %s", sapi_ex)
                            finally:
                                self._active_engine = None
                                try:
                                    del temp_engine
                                except:
                                    pass
                elif self._engine_type == "PPASO":
                    # 2. 초경량 온디바이스 합성 엔진 (Ppaso-TTS)
                    temp_file = os.path.join(self._temp_dir, f"ppaso_{int(time.time()*1000)}.wav")
                    target_speed = speed if isinstance(speed, (int, float)) and speed < 3.0 else 1.0
                    if self._ppaso_engine and self._ppaso_engine.speak_to_file(text, temp_file, lang=lang, speed=target_speed):
                        try:
                            pygame.mixer.music.load(temp_file)
                            pygame.mixer.music.play()
                            while pygame.mixer.music.get_busy():
                                if self._stop_event.is_set():
                                    pygame.mixer.music.stop()
                                    break
                                time.sleep(0.05)
                            pygame.mixer.music.unload()
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

    def speak(self, text, lang='ko', speed=None):
        """텍스트를 큐에 추가하여 순차적으로 음성 출력. speed가 지정되지 않으면 객체 생성시의 기본값 사용."""
        if not text: return
        target_speed = speed if speed is not None else self._rate
        self._queue.put((text, lang, target_speed))

    def speak_async(self, text, lang='ko', speed=None):
        """비동기 방식으로 호환성 유지"""
        self.speak(text, lang, speed)

    def warmup(self):
        """음성 엔진 초기 지연 방지를 위한 모델 예열"""
        if self._engine_type == "MELO" and self._melo_engine:
            # 딥러닝 기반 모델은 미리 메모리에 로드
            self._melo_engine.get_model('ko')
            self._melo_engine.get_model('en')
        elif self._engine_type == "PPASO" and self._ppaso_engine:
            pass  # Ppaso-TTS는 초기화 시점에 ONNX 모델이 메모리에 즉시 준비됩니다.
        elif self._engine_type == "PYTTSX3":
            # SAPI 엔진은 가벼운 빈 문장으로 초기화 확인
            self.speak_async(" ")

    def is_speaking(self):
        """현재 음성이 합성/재생 중이거나 대기열에 작업이 남아있는지 확인합니다."""
        return self._is_speaking or not self._queue.empty()

    def wait_until_idle(self, timeout=None, poll_interval=0.05):
        """대기열과 현재 합성이 모두 끝날 때까지 대기. timeout 초과면 False 반환."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            # Queue.unfinished_tasks에는 현재 처리 중인 항목도 포함된다.
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
                # stop()의 경우, 이미 speak 루프 내에서 락을 쥔 상태이므로 락을 획득했을 때만 중단 명령 전달
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

if __name__ == "__main__":
    # 고품질 TTS 엔진 테스트
    tts = TTSHelper()
    print("MeloTTS 고품질 음성 테스트...")
    tts.speak("안녕하세요. 딥러닝 기반의 새로운 음성 엔진을 테스트하고 있습니다.", "ko")
    tts.speak("두 번째 문장입니다. 자연스러운 억양을 확인해 보세요.", "ko")
    
    # 작업 완료 대기
    time.sleep(20)
    print("테스트 종료.")
