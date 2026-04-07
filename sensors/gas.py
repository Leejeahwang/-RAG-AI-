"""
MQ-135 가스 감지 센서 모듈 (재황님 담당)

Phase 1: PC에서 시뮬레이션
Phase 3: 라즈베리파이 GPIO 연동
"""

import random
import config


def read_gas_level(simulate=False):
    """
    가스 센서 값을 읽어옵니다.

    Args:
        simulate: True면 시뮬레이션 값 반환, False면 실제 GPIO 읽기

    Returns:
        int: 가스 농도 (아날로그 0~1023)
    """
    if simulate:
        return random.randint(100, 200)

    try:
        from gpiozero import MCP3008
    except ImportError:
        print("⚠️ [경고] gpiozero 라이브러리가 없습니다.")
        return read_gas_level(simulate=True)

    try:
        # MQ-135는 보통 다른 채널(예: 채널 1)에서 읽기
        adc = MCP3008(channel=1)
        value = int(adc.value * 1023)
        adc.close()
        return value
    except Exception as e:
        print(f"❌ [오류] 가스 센서에서 값을 읽어오지 못했습니다: {e}")
        return read_gas_level(simulate=True)


def is_gas_detected(value=None):
    """가스 임계값 초과 여부 판단"""
    if value is None:
        value = read_gas_level()
    return value > config.SENSOR_THRESHOLDS["gas_mq135"]
