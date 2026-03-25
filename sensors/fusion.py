"""
멀티센서 퓨전 모듈 (규태님 + 재황님 담당)

여러 센서 데이터를 종합하여 위험도 Level 1~5를 산정합니다.
"""

import config


def calculate_risk_level(smoke_val, gas_val, temp_data, fire_detected_by_camera=False):
    """
    멀티센서 데이터를 종합하여 위험도 등급을 산정합니다.

    Args:
        smoke_val: MQ-2 연기센서 값
        gas_val: MQ-135 가스센서 값
        temp_data: {"temperature": float, "humidity": float}
        fire_detected_by_camera: Vision AI가 화재를 감지했는지 여부

    Returns:
        dict: {"level": int, "label": str, "details": str}

    TODO (규태님 + 재황님):
        - 센서 조합별 세부 판정 로직 고도화
        - 시간에 따른 값 변화율(급증) 반영
    """
    thresholds = config.SENSOR_THRESHOLDS
    triggered_sensors = []

    if smoke_val > thresholds["smoke_mq2"]:
        triggered_sensors.append("연기")
    if gas_val > thresholds["gas_mq135"]:
        triggered_sensors.append("가스")
    if temp_data["temperature"] > thresholds["temperature_high"]:
        triggered_sensors.append("고온")

    count = len(triggered_sensors)

    # 위험도 등급 산정
    if count == 0 and not fire_detected_by_camera:
        level = 0
    elif count == 1 and not fire_detected_by_camera:
        level = 1  # 주의
    elif count == 1 and fire_detected_by_camera:
        level = 3  # 위험 (센서 1개 + 카메라 확인)
    elif count >= 2 and not fire_detected_by_camera:
        level = 2  # 경고
    elif count >= 2 and fire_detected_by_camera:
        level = 4  # 긴급
    else:
        level = 1

    label = config.RISK_LEVELS.get(level, "정상")
    details = f"반응 센서: {', '.join(triggered_sensors) if triggered_sensors else '없음'}"
    if fire_detected_by_camera:
        details += " + 카메라 화재 확인"

    return {"level": level, "label": label, "details": details}
