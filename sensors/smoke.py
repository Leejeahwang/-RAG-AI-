"""
MQ-2 연기 감지 센서 모듈 (재황님 담당)

Phase 1: PC에서 시뮬레이션 (랜덤 값 생성)
Phase 3: 라즈베리파이 GPIO 연동 (ADC 사용)
"""

import random
import time
import config

_smoke_history = []
FILTER_SIZE = 5


def read_smoke_level(simulate=True):
    """
    연기 센서 값을 읽어옵니다. (이동 평균 필터 적용)

    Args:
        simulate: True면 시뮬레이션 값 반환, False면 실제 GPIO 읽기

    Returns:
        int: 필터링된 연기 농도 (아날로그 0~1023)
    """
    global _smoke_history
    
    if simulate:
        raw_value = random.randint(50, 150)  # 평상시 범위
    else:
        try:
            from gpiozero import MCP3008
        except ImportError:
            print("⚠️ [경고] gpiozero 라이브러리가 없습니다.")
            return read_smoke_level(simulate=True)

        try:
            # 통신 오류 방지를 위한 예외 처리 강화
            adc = MCP3008(channel=0)
            raw_value = int(adc.value * 1023)
            adc.close()
        except Exception as e:
            print(f"❌ [오류] 연기 센서 SPI/I2C 통신 실패, 재시도 중... : {e}")
            time.sleep(0.1)  # 짧은 대기 후 Fallback
            return read_smoke_level(simulate=True)

    # 노이즈 제거를 위한 이동 평균 필터(Moving Average Filter) 적용
    _smoke_history.append(raw_value)
    if len(_smoke_history) > FILTER_SIZE:
        _smoke_history.pop(0)

    filtered_value = int(sum(_smoke_history) / len(_smoke_history))
    return filtered_value


def is_smoke_detected(value=None):
    """연기 임계값 초과 여부 판단"""
    if value is None:
        value = read_smoke_level()
    return value > config.SENSOR_THRESHOLDS["smoke_mq2"]
