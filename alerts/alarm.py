"""
경보 출력 모듈 (재황님 담당)

부저/스피커 및 LED를 통한 경보 출력을 담당합니다.
Phase 1: 콘솔 출력으로 시뮬레이션
Phase 3: GPIO를 통해 실제 부저/LED 제어
"""

import config
import math
import struct
import threading
import time
import pygame

_siren_thread = None
_siren_playing = False
_siren_stop_requested = False
_siren_sound = None

def _init_siren():
    global _siren_sound
    import os
    
    # 1. 커스텀 사이렌 파일 로드 시도
    file_path = getattr(config, 'SIREN_FILE_PATH', '')
    if file_path and os.path.exists(file_path):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            _siren_sound = pygame.mixer.Sound(file_path)
            return
        except Exception as e:
            print(f"⚠️ [커스텀 사이렌 파일 로드 실패] {e}, 기본 합성음으로 대체합니다.")
            
    # 2. 파일이 없거나 로드 실패 시 주파수 합성음 생성
    if _siren_sound is not None:
        return
        
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=22050, size=-16, channels=1)
        
        # 2초짜리 주파수 변조(LFO) 사이렌 소리 생성 (600Hz ~ 1000Hz 왕복)
        duration = 2.0
        sample_rate = 22050
        num_samples = int(duration * sample_rate)
        buffer = bytearray()
        
        for i in range(num_samples):
            t = i / sample_rate
            # 1.5Hz 주기로 주파수 변환
            lfo = (math.sin(2 * math.pi * 1.5 * t) + 1.0) / 2.0
            freq = 600.0 * (1.0 - lfo) + 1000.0 * lfo
            # 음량이 너무 크지 않게 8192로 조절
            val = int(8192 * math.sin(2 * math.pi * freq * t))
            buffer.extend(struct.pack('<h', val))
            
        _siren_sound = pygame.mixer.Sound(buffer=bytes(buffer))
    except Exception as e:
        print(f"⚠️ [사이렌 합성 실패] {e}")

def _siren_loop():
    global _siren_playing, _siren_stop_requested
    
    _init_siren()
    if not _siren_sound:
        _siren_playing = False
        _siren_stop_requested = False
        return
    
    try:
        # 볼륨 조절 반영
        volume = getattr(config, 'SIREN_VOLUME', 0.25)
        _siren_sound.set_volume(volume)
        
        channel = _siren_sound.play(loops=-1)  # 무한 반복 재생
        start_time = time.time()
        
        while _siren_playing:
            elapsed = time.time() - start_time
            min_duration = getattr(config, 'SIREN_MIN_DURATION', 10.0)
            
            # 정지 요청이 들어왔고, 최소 유지 시간이 경과했다면 사이렌을 종료합니다.
            if _siren_stop_requested and elapsed >= min_duration:
                break
                
            time.sleep(0.1)
            
        if channel:
            channel.stop()
    except Exception as e:
        print(f"⚠️ [사이렌 재생 중 에러] {e}")
    finally:
        _siren_playing = False
        _siren_stop_requested = False

def start_siren():
    """사이렌을 백그라운드에서 반복 재생합니다."""
    global _siren_thread, _siren_playing, _siren_stop_requested
    if _siren_playing:
        _siren_stop_requested = False
        return
    _siren_playing = True
    _siren_stop_requested = False
    _siren_thread = threading.Thread(target=_siren_loop, daemon=True)
    _siren_thread.start()

def stop_siren():
    """재생 중인 사이렌에 정지 신호를 보냅니다 (설정된 최소 유지 시간 경과 후 정지됨)."""
    global _siren_stop_requested
    _siren_stop_requested = True

def trigger_alarm(risk_level, message=""):
    """
    위험도에 따라 경보를 발령합니다.

    Args:
        risk_level: 위험도 등급 (1~5)
        message: 경보 메시지
    """
    label = config.RISK_LEVELS.get(risk_level, "알 수 없음")
    print(f"\n🚨 [경보 Level {risk_level} - {label}] {message}")

    if risk_level >= 3:
        print("   🔔 부저 작동! (시뮬레이션)")
    if risk_level >= 4:
        print("   📢 전관 방송 작동 및 사이렌 재생! (시뮬레이션)")
        start_siren()


def stop_alarm():
    """경보를 중지합니다."""
    print("🔕 경보 해제")
    stop_siren()
