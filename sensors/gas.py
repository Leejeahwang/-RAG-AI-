"""
MQ-135 가스 감지 센서 모듈 (재황님 담당)

Phase 1: PC에서 시뮬레이션
Phase 3: 라즈베리파이 GPIO 연동
"""

import random
import config


def read_gas_level(simulate=True):
    """
    가스 센서 값을 읽어옵니다.

    Returns:
        int: 가스 농도 (아날로그 0~1023)

    TODO (재황님):
        Phase 3에서 MQ-135 + MCP3008 ADC 연동
    """
    if simulate:
        return random.randint(100, 200)

    raise NotImplementedError("GPIO 연동은 라즈베리파이에서 구현 예정")


def is_gas_detected(value=None):
    """가스 임계값 초과 여부 판단"""
    if value is None:
        value = read_gas_level()
    return value > config.SENSOR_THRESHOLDS["gas_mq135"]
