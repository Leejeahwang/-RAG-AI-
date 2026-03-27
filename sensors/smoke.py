"""
MQ-2 연기 감지 센서 모듈 (재황님 담당)

Phase 1: PC에서 시뮬레이션 (랜덤 값 생성)
Phase 3: 라즈베리파이 GPIO 연동 (ADC 사용)
"""

import random
import config


def read_smoke_level(simulate=True):
    """
    연기 센서 값을 읽어옵니다.

    Args:
        simulate: True면 시뮬레이션 값 반환, False면 실제 GPIO 읽기

    Returns:
        int: 연기 농도 (아날로그 0~1023)

    TODO (재황님):
        Phase 3에서 실제 MQ-2 센서 + MCP3008 ADC 연동
        - spidev 또는 gpiozero 라이브러리 사용
        - MCP3008 채널 0번에서 아날로그 값 읽기
    """
    if simulate:
        return random.randint(50, 150)  # 평상시 범위

    # TODO: 실제 GPIO 코드
    raise NotImplementedError("GPIO 연동은 라즈베리파이에서 구현 예정")


def is_smoke_detected(value=None):
    """연기 임계값 초과 여부 판단"""
    if value is None:
        value = read_smoke_level()
    return value > config.SENSOR_THRESHOLDS["smoke_mq2"]
