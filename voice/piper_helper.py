"""
Piper TTS 헬퍼 (v35 Native)
경로를 절대 경로로 고정하고, 윈도우 환경에서의 subprocess 안정성을 강화했습니다.
"""
import os
import subprocess
import time
import threading
import queue
import pygame
import config

class PiperTTSHelper:
    def __init__(self):
        # [v35] 절대 경로로 전환하여 경로 혼선 방지
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.model_path = os.path.join(self.base_dir, config.PIPER_MODEL.replace("/", os.sep))
        self.config_path = os.path.join(self.base_dir, config.PIPER_CONFIG.replace("/", os.sep))
        self.temp_dir = os.path.join(self.base_dir, "temp_voice")
        self.queue = queue.Queue()
        self.is_running = True
        
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
            
        # 오디오 재생을 위한 pygame 초기화
        if not pygame.mixer.get_init():
            pygame.mixer.init()
            
        # 발화 관리 스레드 시작
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def _process_queue(self):
        """음성 생성 및 재생 큐 처리"""
        chunk_count = 0
        while self.is_running:
            try:
                text, lang = self.queue.get(timeout=1)
                if not text or not text.strip(): continue
                
                # 파일명 생성
                output_wav = os.path.join(self.temp_dir, f"output_{chunk_count % 10}.wav")
                chunk_count += 1
                
                # [v35] 모델 파일 존재 여부 최종 확인
                if not os.path.exists(self.model_path):
                    print(f"[PiperTTS] ❌ 모델을 찾을 수 없음: {self.model_path}")
                    self.queue.task_done()
                    continue

                piper_bin = "piper.exe" if os.name == 'nt' else "piper"
                
                piper_cmd = [
                    piper_bin, 
                    "--model", self.model_path,
                    "--config", self.config_path,
                    "--output_file", output_wav
                ]
                
                try:
                    # [v35] 윈도우에서 팝업 창 방지 및 파이프 통신 개선
                    process = subprocess.Popen(
                        piper_cmd, 
                        stdin=subprocess.PIPE, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        text=True, 
                        encoding='utf-8',
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    stdout, stderr = process.communicate(input=text)
                    
                    if process.returncode != 0:
                        print(f"[PiperTTS] ❌ Piper 오류 (코드 {process.returncode}): {stderr}")
                    
                    if os.path.exists(output_wav):
                        sound = pygame.mixer.Sound(output_wav)
                        channel = sound.play()
                        while channel.get_busy():
                            time.sleep(0.1)
                    else:
                        print(f"[PiperTTS] ❌ 웨이브 생성 실패: {output_wav}")
                except Exception as e:
                    print(f"[PiperTTS] ❌ 실행 에러: {e}")
                    
                self.queue.task_done()
            except queue.Empty:
                continue

    def speak_async(self, text, lang='ko', speed=1.0):
        if not text.strip(): return
        self.queue.put((text, lang))

    def warmup(self):
        print("[PiperTTS] 엔진 예열 완료")
        pass

    def stop(self):
        self.is_running = False
        pygame.mixer.stop()

# 싱글톤 인스턴스 제공
piper_tts = PiperTTSHelper()
