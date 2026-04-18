import os
import sys
import re
import queue
import threading
import time
import tempfile
import pygame
from voice.melo_wrapper import MeloEngine

class TTSHelper:
    """
    TTSHelper: MeloTTS 기반 고품질 다국어 음성 합성 모듈
    ======================================================================
    - MeloEngine을 사용하여 딥러닝 기반의 자연스러운 음성 생성
    - Pygame Mixer를 사용하여 오디오 재생 및 중단 제어
    - 대기열(Queue) 방식을 통해 문장 단위의 실시간 스트리밍 재생 지원
    """
    def __init__(self, rate=1.0, volume=1.0):
        self._rate = rate
        self._volume = volume
        
        # MeloTTS 엔진 로드 (최초 호출 시 모델 다운로드 발생 가능)
        self._engine = MeloEngine()
        
        # 오디오 재생기 엔진 초기화
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"[TTS] 오디오 장치 초기화 실패: {e}")

        # 큐 및 스레드 설정
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._is_speaking = False
        
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        
        # 임시 파일 저장소
        self._temp_dir = os.path.join(tempfile.gettempdir(), "edge_saver_tts")
        os.makedirs(self._temp_dir, exist_ok=True)
        
        print(f"[TTS] MeloTTS 최적화 엔진 준비 완료 (속도: {self._rate}x).")

    def _worker(self):
        """백그라운드에서 큐를 감시하며 순차적으로 음성을 합성하고 재생합니다."""
        while not self._stop_event.is_set():
            try:
                # 큐에서 작업 가져오기 (timeout을 주어 주기적으로 stop_event 확인)
                item = self._queue.get(timeout=0.2)
                if item is None: break
                
                # 큐 아이템 파싱 (text, lang, speed)
                if len(item) == 3:
                    text, lang, speed = item
                else:
                    text, lang = item
                    speed = self._rate # 기본값 사용
                
                text = self._sanitize_text(text)
                if not text:
                    self._queue.task_done()
                    continue
                
                self._is_speaking = True
                
                # 임시 결과 파일 경로
                temp_file = os.path.join(self._temp_dir, f"melo_{int(time.time()*1000)}.wav")
                
                # 1. 고품질 음성 합성 (MeloTTS)
                success = self._engine.speak_to_file(text, temp_file, lang=lang, speed=speed)
                
                if success and os.path.exists(temp_file):
                    # 2. 오디오 출력 (Pygame)
                    try:
                        pygame.mixer.music.load(temp_file)
                        pygame.mixer.music.set_volume(self._volume)
                        pygame.mixer.music.play()
                        
                        # 재생 완료될 때까지 대기
                        while pygame.mixer.music.get_busy():
                            if self._stop_event.is_set():
                                pygame.mixer.music.stop()
                                break
                            time.sleep(0.05)
                        
                        pygame.mixer.music.unload()
                    except Exception as e:
                        print(f"[TTS] 재생 오류: {e}")
                    
                    # 사용 완료된 임시 파일 삭제
                    try: os.remove(temp_file)
                    except: pass
                
                self._is_speaking = False
                self._queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                # 무한 루프 방지 및 에러 로깅
                time.sleep(1)

    def _sanitize_text(self, text):
        """음성 출력을 위해 불필요한 특수문자 및 마크다운 기호 제거"""
        if not text: return ""
        # 1. 마크다운 강조 기호(*)는 여백 없이 제거
        text = text.replace('*', '')
        # 2. 콜론(:)은 자연스러운 이음새를 위해 공백 하나로 치환 (쉼표보다 짧은 뜸)
        text = text.replace(':', ' ')
        # 3. 기타 마크다운 특수 기호 제거
        text = re.sub(r'[#\-\|_`>]', ' ', text)
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

    def stop(self):
        """현재 진행 중인 재생을 즉시 멈추고 대기열을 비웁니다."""
        # 1. 대기열 비우기
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        
        # 2. 현재 재생 중인 음악 중단
        try:
            if pygame.mixer.get_init():
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
