"""
경보 출력 모듈 (재황님 담당)

부저/스피커 및 LED를 통한 경보 출력을 담당합니다.
Phase 1: 콘솔 출력으로 시뮬레이션
Phase 3: GPIO를 통해 실제 부저/LED 제어
"""

import config


def trigger_alarm(risk_level, message=""):
    """
    위험도에 따라 경보를 발령합니다.

    Args:
        risk_level: 위험도 등급 (1~5)
        message: 경보 메시지

    TODO (재황님):
        Phase 3에서 GPIO 부저/LED 제어
        - Level 1~2: LED 점등
        - Level 3+: 부저 + LED
        - Level 4+: 전관 방송 연동
    """
    label = config.RISK_LEVELS.get(risk_level, "알 수 없음")
    print(f"\n🚨 [경보 Level {risk_level} - {label}] {message}")

    if risk_level >= 3:
        print("   🔔 부저 작동! (시뮬레이션)")
    if risk_level >= 4:
        print("   📢 전관 방송 작동! (시뮬레이션)")


def stop_alarm():
    """경보를 중지합니다."""
    print("🔕 경보 해제")
