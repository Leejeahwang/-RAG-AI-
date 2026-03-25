"""
DHT22 온도/습도 센서 모듈 (재황님 담당)

Phase 1: PC에서 시뮬레이션
Phase 3: 라즈베리파이 GPIO 연동 (Adafruit_DHT)
"""

import random
import config


def read_temperature(simulate=True):
    """
    온도/습도 센서 값을 읽어옵니다.

    Returns:
        dict: {"temperature": float, "humidity": float}

    TODO (재황님):
        Phase 3에서 DHT22 센서 연동
        - pip install Adafruit_DHT
        - GPIO 핀 지정 후 읽기
    """
    if simulate:
        return {
            "temperature": round(random.uniform(20.0, 30.0), 1),
            "humidity": round(random.uniform(40.0, 60.0), 1),
        }

    raise NotImplementedError("GPIO 연동은 라즈베리파이에서 구현 예정")


def is_temperature_abnormal(data=None):
    """온도 이상 여부 판단"""
    if data is None:
        data = read_temperature()
    return data["temperature"] > config.SENSOR_THRESHOLDS["temperature_high"]
