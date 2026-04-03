"""
경보 출력 모듈 (재황님 담당)

부저/스피커 및 LED를 통한 경보 출력을 담당합니다.
Phase 1: 콘솔 출력으로 시뮬레이션
Phase 3: GPIO를 통해 실제 부저/LED 제어
"""

import config

# Mac (로컬) 테스트 시 RPi.GPIO가 없어도 죽지 않도록 예외 처리
TRY_GPIO = True
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(config.ALERT_BUZZER_PIN, GPIO.OUT)
    GPIO.setup(config.ALERT_LED_PIN, GPIO.OUT)
    GPIO_AVAILABLE = True
except ImportError:
    print("⚠️ [경고] RPi.GPIO 라이브러리가 없습니다. (시뮬레이션 모드로 작동합니다)")
    GPIO_AVAILABLE = False


def trigger_alarm(risk_level, message=""):
    """
    위험도에 따라 경보를 발령합니다.
    """
    label = config.RISK_LEVELS.get(risk_level, "알 수 없음")
    print(f"\n🚨 [경보 Level {risk_level} - {label}] {message}")

    if risk_level >= 1 and GPIO_AVAILABLE:
        # 주의(1) 이상: LED 점등
        GPIO.output(config.ALERT_LED_PIN, GPIO.HIGH)

    if risk_level >= 3:
        if GPIO_AVAILABLE:
            GPIO.output(config.ALERT_BUZZER_PIN, GPIO.HIGH)
        else:
            print("   🔔 부저 작동! (시뮬레이션)")
            
    if risk_level >= 4:
        print("   📢 전관 방송 작동! (시뮬레이션 - API 연동 예정)")


def stop_alarm():
    """경보를 중지합니다."""
    print("🔕 경보 해제")
    if GPIO_AVAILABLE:
        GPIO.output(config.ALERT_BUZZER_PIN, GPIO.LOW)
        GPIO.output(config.ALERT_LED_PIN, GPIO.LOW)
