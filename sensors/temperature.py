"""
DHT22 온도/습도 센서 모듈 (재황님 담당)

Phase 1: PC에서 시뮬레이션
Phase 3: 라즈베리파이 GPIO 연동 (Adafruit_DHT)
"""

import random
import config


def read_temperature(simulate=False, pin=4):
    """
    온도/습도 센서 값을 읽어옵니다.

    Args:
        simulate (bool): True이면 가상 랜덤값을 반환 (로컬 개발용)
        pin (int): DHT11이 연결된 라즈베리파이 BCM GPIO 핀 번호 (기본값: GPIO4)
    """
    if simulate:
        return {
            "temperature": round(random.uniform(20.0, 30.0), 1),
            "humidity": round(random.uniform(40.0, 60.0), 1),
        }

    try:
        import Adafruit_DHT
    except ImportError:
        print("⚠️ [경고] Adafruit_DHT 라이브러리가 없습니다.")
        return read_temperature(simulate=True)

    # 라즈베리파이 진짜 센서(DHT11) 읽기 시도
    sensor = Adafruit_DHT.DHT11
    humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)

    if humidity is not None and temperature is not None:
        return {
            "temperature": round(temperature, 1),
            "humidity": round(humidity, 1)
        }
    else:
        print("❌ [오류] DHT11 센서에서 값을 읽어오지 못했습니다.")
        # 실패 시 프로그램이 죽지 않게 가짜 값 반환
        return read_temperature(simulate=True)


def is_temperature_abnormal(data=None):
    """온도 이상 여부 판단"""
    if data is None:
        data = read_temperature()
    return data["temperature"] > config.SENSOR_THRESHOLDS["temperature_high"]
