"""
멀티센서 퓨전 모듈 (규태님 + 재황님 담당)

여러 센서 데이터를 종합하여 위험도 Level 1~5를 산정합니다.
"""

import config


def calculate_risk_level(smoke_val, gas_val, temp_data, vision_input=False, fire_detected_by_camera=None):
    """
    멀티센서 데이터와 비전 동역학 분석 결과를 종합하여 위험도 등급(Level 0~5)을 산정합니다.

    Args:
        smoke_val: MQ-2 연기센서 값
        gas_val: MQ-135 가스센서 값
        temp_data: {"temperature": float, "humidity": float}
        vision_input: bool 또는 dict 형태의 비전 분석 결과
        fire_detected_by_camera: [하위 호환용] 기존 키워드 인자 지원
            - bool인 경우: 기존 호환성 유지 (fire_detected 여부)
            - dict인 경우: {
                "fire_detected": bool,          # 불꽃/연기 최종 확정 여부
                "is_real_smoke": bool,          # 상방 대류가 검증된 진짜 연기 (조기 감지)
                "is_static_photo": bool,        # 정지 사진/모니터 오탐 여부
                "pre_hazard_alert": str,        # 클라우드 VLM 전조 위험 (전열기 방치 등)
                "description": str
              }

    Returns:
        dict: {"level": int, "label": str, "details": str, "is_early_detection": bool}
    """
    thresholds = config.SENSOR_THRESHOLDS
    triggered_sensors = []

    if smoke_val > thresholds["smoke_mq2"]:
        triggered_sensors.append("연기센서(천장)")
    if gas_val > thresholds["gas_mq135"]:
        triggered_sensors.append("가스센서")
    if temp_data["temperature"] > thresholds["temperature_high"]:
        triggered_sensors.append("고온감지")

    sensor_count = len(triggered_sensors)

    if fire_detected_by_camera is not None:
        vision_input = fire_detected_by_camera

    # 비전 정보 파싱 (하위 호환성 유지)
    if isinstance(vision_input, dict):
        fire_detected = vision_input.get("fire_detected", False)
        is_real_smoke = vision_input.get("is_real_smoke", False)
        is_static_photo = vision_input.get("is_static_photo", False)
        pre_hazard_alert = vision_input.get("pre_hazard_alert", "")
        vision_desc = vision_input.get("description", "")
    else:
        fire_detected = bool(vision_input)
        is_real_smoke = False
        is_static_photo = False
        pre_hazard_alert = ""
        vision_desc = ""

    is_early_detection = False
    details_list = []

    # 1. 사진 오탐 차단 (정지된 스마트폰/인쇄 사진 감지 시)
    if is_static_photo and not is_real_smoke:
        if sensor_count == 0:
            return {
                "level": 0,
                "label": "정상",
                "details": "🛡️ 카메라 정지 사진 감지 (움직임 없음 - 오경보 차단 중)",
                "is_early_detection": False
            }
        else:
            # 센서만 울리고 비전은 가짜 사진인 경우: 센서 단독 레벨로 제한
            fire_detected = False

    # 2. 위험도 등급 산정 (교차 검증 및 조기 감지 로직)
    if sensor_count == 0:
        if not fire_detected and not is_real_smoke:
            if pre_hazard_alert:
                # [신규] 불나기 전 전조 감지 (VLM 기반 전열기 방치 등)
                level = 1
                details_list.append(f"⚠️ 화재 전조 주의: {pre_hazard_alert}")
                is_early_detection = True
            else:
                level = 0
                details_list.append("모든 센서 및 비전 정상")
        elif is_real_smoke and not fire_detected:
            # [핵심 신규] 미세 훈소 연기 조기 감지! (천장 센서는 아직 0단계)
            level = 2
            details_list.append("🚨 [비전 조기 감지] 피어오르는 미세 연기 기둥 포착 (센서 도달 전 선제 경보)")
            is_early_detection = True
        elif fire_detected:
            # 카메라 불꽃 단독 감지 (센서 대기)
            level = 2
            details_list.append("카메라 화재 감지 (센서 교차 검증 대기)")
        else:
            level = 0

    elif sensor_count == 1:
        if not fire_detected and not is_real_smoke:
            level = 1  # 센서 1개 단독 이상치
            details_list.append(f"센서 단독 반응: {', '.join(triggered_sensors)}")
        elif is_real_smoke and not fire_detected:
            # 센서 1개 + 미세 연기 확산 확인 -> 긴급 격상!
            level = 4
            details_list.append(f"🔥 초기 훈소 화재 확정! (비전 연기 상승 + {', '.join(triggered_sensors)})")
            is_early_detection = True
        else:
            # 센서 1개 + 불꽃 확인 -> 진짜 화재 확정
            level = 4
            details_list.append(f"🔥 실제 화재 확정! (카메라 화재 + {', '.join(triggered_sensors)})")

    else: # sensor_count >= 2 (센서 복합 반응)
        if not fire_detected and not is_real_smoke:
            level = 3  # 센서 다중 감지 (비전 미확인)
            details_list.append(f"센서 복합 반응: {', '.join(triggered_sensors)}")
        else:
            level = 5  # 재난 단계 (다중 센서 + 비전 화재/훈소 확정)
            details_list.append(f"🚨 대형 재난 화재 확정! (비전 감지 + {', '.join(triggered_sensors)})")

    label = config.RISK_LEVELS.get(level, "정상")
    if vision_desc and "로컬 감지" in vision_desc:
        details_list.append(f"AI 진단: {vision_desc}")

    return {
        "level": level,
        "label": label,
        "details": " | ".join(details_list),
        "is_early_detection": is_early_detection
    }
