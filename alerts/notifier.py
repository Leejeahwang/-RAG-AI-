"""
관제실 알림 전송 모듈 (재황님 담당)

화재 감지 시 관제실에 상세 알림을 전송합니다.
Phase 1: 콘솔 출력
Phase 2+: MQTT 또는 HTTP API를 통한 실제 전송
"""


def send_alert(zone, risk_level, sensor_details, ai_guidance=""):
    """
    관제실에 알림을 전송합니다.

    Args:
        zone: 감지 구역 (예: "B동 3층 전기실")
        risk_level: 위험도 등급
        sensor_details: 센서 상세 정보 문자열
        ai_guidance: LLM이 생성한 대응 지침

    TODO (재황님):
        - Phase 2: MQTT 프로토콜로 관제실 대시보드에 실시간 전송
        - Phase 3: RPi 간 메시 네트워크 연쇄 경보
    """
    print("\n" + "=" * 55)
    print(f"📱 [관제실 알림 전송]")
    print(f"   위치: {zone}")
    print(f"   위험도: Level {risk_level}")
    print(f"   센서: {sensor_details}")
    if ai_guidance:
        print(f"   AI 대응 지침: {ai_guidance[:100]}...")
    print("=" * 55)
