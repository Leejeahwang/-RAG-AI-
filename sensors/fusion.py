"""Sensor corroboration for verified flame and early rising-smoke evidence."""
import config


def calculate_risk_level(smoke_val, gas_val, temp_data, vision_input=False, fire_detected_by_camera=None):
    """Fuse detector v1 evidence; continue accepting legacy bool/dict callers.

    With normal sensors, verified flame or smoke gives Level 2 local warning.
    One abnormal sensor corroborates it at Level 4; two or more give Level 5.
    A candidate/error/blocked photo does not corroborate abnormal sensors.
    """
    thresholds = config.SENSOR_THRESHOLDS
    triggered = []
    if smoke_val > thresholds["smoke_mq2"]:
        triggered.append("연기센서(천장)")
    if gas_val > thresholds["gas_mq135"]:
        triggered.append("가스센서")
    if temp_data["temperature"] > thresholds["temperature_high"]:
        triggered.append("고온감지")
    if fire_detected_by_camera is not None:
        vision_input = fire_detected_by_camera
    if isinstance(vision_input, dict):
        versioned = "contract_version" in vision_input
        fire = bool(vision_input.get("is_real_fire", False)) if versioned else bool(
            vision_input.get("is_real_fire", False) or vision_input.get("fire_detected", False))
        smoke = bool(vision_input.get("is_real_smoke", False))
        # Old detectors used fire_detected=True for early smoke as well.
        if not versioned and smoke and "is_real_fire" not in vision_input:
            fire = False
        demo = bool(vision_input.get("demo_bypass")) and config.SENSOR_MODE == "demo"
        blocked = bool(vision_input.get("is_static_photo"))
        status = vision_input.get("status", "")
        if (status.endswith("ERROR") or status in {"MODEL_NOT_INITIALIZED", "NO_RESULT",
                "INVALID_INPUT", "FILE_NOT_FOUND", "CAMERA_OFFLINE"} or blocked):
            fire = smoke = demo = False
        pre_hazard = vision_input.get("pre_hazard_alert", "")
    else:
        fire, smoke, demo, blocked, pre_hazard = bool(vision_input), False, False, False, ""
    confirmed = fire or smoke or demo
    early = smoke and not fire and not demo
    count = len(triggered)
    if confirmed:
        level = 2 if count == 0 else 4 if count == 1 else 5
        evidence = "[시연 우회] 화재 후보" if demo else "검증된 불꽃" if fire else "[비전 조기 감지] 상방 확산 연기"
        details = f"{evidence} | " + (f"센서 교차 검증: {', '.join(triggered)}" if count else "센서 반응 전 선제 경고")
    elif count:
        level = 1 if count == 1 else 3
        details = f"센서 {'단독' if count == 1 else '복합'} 반응: {', '.join(triggered)}"
    elif pre_hazard:
        level, details, early = 1, f"화재 전조 주의: {pre_hazard}", True
    else:
        level = 0
        details = "카메라 사진/강체 오탐 차단 중" if blocked else "확정된 센서 및 비전 위험 없음"
    return dict(level=level, label=config.RISK_LEVELS.get(level, "정상"), details=details,
                is_early_detection=early, vision_confirmed=confirmed,
                vision_kind="demo" if demo else "fire" if fire else "smoke" if smoke else "none")
