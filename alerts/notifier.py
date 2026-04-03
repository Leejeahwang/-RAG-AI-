"""
관제실 알림 전송 모듈 (재황님 담당)

화재 감지 시 관제실에 상세 알림을 전송합니다.
Phase 1: 콘솔 출력
Phase 2: MQTT를 통한 실제 전송 (구현됨)
"""

import json
import time
import config

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    print("⚠️ [경고] paho-mqtt 라이브러리가 없습니다. 관제실 전송은 콘솔 출력으로만 대체됩니다.")
    MQTT_AVAILABLE = False


def send_alert(zone, risk_level, sensor_details, ai_guidance=""):
    """
    관제실에 알림을 전송합니다.
    """
    label = config.RISK_LEVELS.get(risk_level, "알 수 없음")
    
    print("\n" + "=" * 55)
    print(f"📱 [관제실 알림 전송 준비]")
    print(f"   위치: {zone}")
    print(f"   위험도: Level {risk_level} ({label})")
    print(f"   센서: {sensor_details}")
    if ai_guidance:
        print(f"   AI 대응 지침: {ai_guidance[:100]}...")
    print("=" * 55)

    if not MQTT_AVAILABLE:
        print("   >> MQTT 미지원으로 전송 생략됨.")
        return

    # MQTT 메시지(JSON) 구성
    payload = {
        "timestamp": int(time.time()),
        "zone": zone,
        "risk_level": risk_level,
        "risk_label": label,
        "sensor_data": sensor_details,
        "ai_guidance": ai_guidance
    }
    
    try:
        client = mqtt.Client()
        # 타임아웃을 짧게 주어 브로커 연결 실패 시 시스템이 멈추지 않게 방지
        client.connect(config.MQTT_BROKER_URL, config.MQTT_BROKER_PORT, 5)
        
        # 메시지 발행 (QoS 1)
        topic = getattr(config, "MQTT_TOPIC_ALERTS", "factory/fire_alerts")
        client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)
        client.disconnect()
        
        print(f'   📡 [MQTT 전송 완료] Topic: {topic}')
    except Exception as e:
        print(f"   ❌ [MQTT 전송 실패] {e}")
