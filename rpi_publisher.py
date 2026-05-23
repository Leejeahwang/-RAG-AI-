"""
rpi_publisher.py - 라즈베리파이에서 실행하는 MQTT 발행 스크립트

센서/카메라 데이터를 읽어 관제 PC MQTT 브로커로 전송.

실행 방법:
    BROKER_HOST=192.168.x.x ZONE=A구역 python rpi_publisher.py

환경변수:
    BROKER_HOST : 관제 PC의 IP 주소 (기본값: config.MQTT_BROKER_HOST)
    ZONE        : 이 Pi의 구역 이름 (기본값: A구역)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

import config

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("❌ paho-mqtt 없음. pip install paho-mqtt 실행 후 재시도")
    sys.exit(1)

from sensors import smoke, gas, temperature
from vision import cctv_service, fire_detector
import cv2

ZONE = os.environ.get("ZONE", "A구역")
BROKER_HOST = os.environ.get("BROKER_HOST", config.MQTT_BROKER_HOST)
BROKER_PORT = config.MQTT_BROKER_PORT

TOPIC_SENSORS = f"{config.MQTT_TOPIC_SENSORS}/{ZONE}"
TOPIC_FIRE = f"{config.MQTT_TOPIC_FIRE}/{ZONE}"


def main() -> None:
    client = mqtt.Client()
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    except Exception as e:
        print(f"❌ 브로커 연결 실패 ({BROKER_HOST}:{BROKER_PORT}): {e}")
        sys.exit(1)

    client.loop_start()
    print(f"✅ [{ZONE}] MQTT 연결 완료 → {BROKER_HOST}:{BROKER_PORT}")

    cam_t = threading.Thread(target=cctv_service.camera_worker_thread, daemon=True)
    cam_t.start()
    print(f"📷 [{ZONE}] 카메라 워커 시작")

    sensor_tick = 0.0
    fire_tick = 0.0

    try:
        while True:
            now = time.time()

            # 센서 — 1초 주기
            if now - sensor_tick >= 1.0:
                try:
                    s_val = smoke.read_smoke_level(simulate=False)
                    g_val = gas.read_gas_level(simulate=False)
                    t_data = temperature.read_temperature(simulate=False)
                    payload = {
                        "zone": ZONE,
                        "smoke": int(s_val),
                        "gas": int(g_val),
                        "temperature": float(t_data.get("temperature", 0)),
                        "humidity": float(t_data.get("humidity", 0)),
                        "ts": now,
                    }
                    client.publish(TOPIC_SENSORS, json.dumps(payload), qos=0)
                    print(f"[{ZONE}] 센서: 온도={payload['temperature']}°C 가스={payload['gas']} 연기={payload['smoke']}")
                except Exception as e:
                    print(f"❌ [{ZONE}] 센서 오류: {e}")
                sensor_tick = now

            # 화재 탐지 — 2초 주기
            if now - fire_tick >= 2.0:
                try:
                    frame = cctv_service.latest_frame
                    if frame is not None:
                        cv2.imwrite(config.CAPTURE_PATH, frame)
                        result = fire_detector.detect_fire(config.CAPTURE_PATH)
                        payload = {
                            "zone": ZONE,
                            "detected": bool(result.get("fire_detected", False)),
                            "confidence": float(result.get("confidence", 0)),
                            "description": str(result.get("description", "")),
                            "ts": now,
                        }
                        client.publish(TOPIC_FIRE, json.dumps(payload), qos=0)
                except Exception as e:
                    print(f"❌ [{ZONE}] 화재탐지 오류: {e}")
                fire_tick = now

            time.sleep(0.1)

    except KeyboardInterrupt:
        print(f"\n🛑 [{ZONE}] 종료")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
