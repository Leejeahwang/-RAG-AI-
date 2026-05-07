import os
import sys
import re
import queue
import threading
import time
import tempfile
import pygame
import pyttsx3
import config
from voice.melo_wrapper import MeloEngine

class TTSHelper:
    """
    TTSHelper: 다중 엔진 지원 지능형 음성 합성 모듈
    ======================================================================
    - [PYTTSX3]: 즉각적인 반응 속도 (SAPI5 기반, 오프라인 전용)
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
        
        # 엔진별 초기화
        self._melo_engine = None
        self._sapi_engine = None
        
        if self._engine_type == "MELO":
            self._melo_engine = MeloEngine()
            try: pygame.mixer.init()
            except: pass
        
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        
        # 임시 파일 저장소 (MeloTTS 전용)
        self._temp_dir = os.path.join(tempfile.gettempdir(), "edge_saver_tts")
        os.makedirs(self._temp_dir, exist_ok=True)
        
        print(f"[TTS] {self._engine_type} 엔진 준비 완료 (속도: {self._rate}).")

    def _worker(self):
        """백그라운드에서 큐를 처리하며 음성을 생성합니다."""
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.2)
                if item is None: break
                
                text, lang, speed = item if len(item) == 3 else (*item, 1.0)
                text = self._sanitize_text(text)
                if not text:
                    self._queue.task_done()
                    continue
                
                self._is_speaking = True
                
                if self._engine_type == "PYTTSX3":
                    # [v17 - 일회용 엔진 전략] 
                    # 문구별로 엔진을 새로 생성하여 스레드 교착 및 상태 고착을 원천 봉쇄합니다.
                    try:
                        temp_engine = pyttsx3.init()
                        # 위험 수치에 따른 동적 속도 조절 반영
                        current_rate = int(self._rate * speed) if isinstance(speed, (int, float)) and speed < 3.0 else self._rate
                        temp_engine.setProperty('rate', current_rate)
                        temp_engine.setProperty('volume', self._volume)
                        
                        temp_engine.say(text)
                        temp_engine.runAndWait()
                        
                        # [자원 해제] 명시적 중단 및 소멸
                        temp_engine.stop()
                        del temp_engine
                    except Exception as sapi_ex:
                        pass
                else:
                    # 2. 고품질 합성 엔진 (MeloTTS)
                    # 2. 고품질 합성 엔진 (MeloTTS)
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
                        except: pass
                
                self._is_speaking = False
                self._queue.task_done()
                
            except queue.Empty: continue
            except Exception as e:
                print(f"[TTS] 워커 에러: {e}")
                time.sleep(1)

    def _sanitize_text(self, text):
        """음성 출력을 위해 불필요한 특수문자 및 마크다운 기호 제거 및 발음 최적화"""
        if not text: return ""
        
        # [품질 향상] 목록 번호 발음 최적화: "1." -> "1번", "2." -> "2번"
        # 묵음 현상을 방지하고 더 자연스러운 안내를 제공합니다.
        text = re.sub(r'(\d+)\.\b', r'\1번', text)
        
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
        elif self._engine_type == "PYTTSX3":
            # SAPI 엔진은 가벼운 빈 문장으로 초기화 확인
            self.speak_async(" ")

    def stop(self):
        """현재 진행 중인 재생을 즉시 멈추고 대기열을 비웁니다."""
        # 1. 대기열 비우기
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        
        # 2. 현재 재생 중인 음성 중단 (엔진별 처리)
        try:
            if self._engine_type == "PYTTSX3" and self._sapi_engine:
                self._sapi_engine.stop()
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
