"""Offline YOLO candidates confirmed by independent smoke/fire motion tracks.

Contract v1: fire_detected/is_real_fire mean verified flame; is_real_smoke
means verified rising smoke. Candidate, warming, blocked and error states never
confirm a hazard. The explicit demo_bypass exception is demo-mode only.
"""
import os
import threading

import config
import cv2
import numpy as np
from vision.smoke_motion import SmokeMotionAnalyzer

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

CONFIDENCE_THRESHOLD = 0.35
model = None
loaded_model_path = config.VISION_MODEL_PATH if os.path.exists(config.VISION_MODEL_PATH) else None
if YOLO is not None and loaded_model_path:
    try:
        model = YOLO(loaded_model_path, task="detect")
    except Exception as exc:
        print(f"[Vision] 모델 초기화 실패: {exc}")
elif loaded_model_path is None:
    print(f"[Vision] 모델 없음: {config.VISION_MODEL_PATH}. tools/export_vision_ncnn.py로 변환하거나 모델 폴더를 배치하세요.")

_lock = threading.RLock()
_motion_analyzers = {
    kind: SmokeMotionAnalyzer(static_motion_ratio=0.04)
    for kind in ("fire", "smoke")
}
_previous_boxes = {}
_last_shape = None


def reset_motion():
    """Discard temporal evidence after missing/stale frames or model errors."""
    global _last_shape
    with _lock:
        for analyzer in _motion_analyzers.values():
            analyzer.reset()
        _previous_boxes.clear()
        _last_shape = None


def _result(status, description, **values):
    result = dict(contract_version=1, fire_detected=False, is_real_fire=False,
                  is_real_smoke=False, is_static_photo=False, demo_bypass=False,
                  confidence=0.0, detected_classes=[], status=status,
                  description=description, box=None, observations=[])
    result.update(values)
    return result


def _overlap(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    area_a = max(0, a[2]-a[0]) * max(0, a[3]-a[1])
    area_b = max(0, b[2]-b[0]) * max(0, b[3]-b[1])
    return intersection / max(1, area_a+area_b-intersection)


def detect_fire(image_input):
    """Return a complete v1 result for a BGR ndarray or image file path.

    Track the strongest candidate per class independently. A missing class or
    disjoint replacement resets its track; this is not multi-object tracking.
    """
    with _lock:
        return _detect_fire(image_input)


def _detect_fire(image_input):
    global _last_shape
    if model is None:
        reset_motion()
        return _result("MODEL_NOT_INITIALIZED", "로컬 화재 모델을 사용할 수 없습니다.")
    if isinstance(image_input, (str, os.PathLike)):
        frame = cv2.imread(os.fspath(image_input))
        if frame is None:
            reset_motion()
            return _result("FILE_NOT_FOUND", "이미지 파일을 읽어올 수 없습니다.")
    elif isinstance(image_input, np.ndarray):
        frame = image_input
    else:
        frame = None
    if (frame is None or frame.dtype != np.uint8 or frame.ndim != 3
            or frame.shape[2] != 3 or min(frame.shape[:2]) < 10):
        reset_motion()
        return _result("INVALID_INPUT", "uint8 BGR 이미지가 필요합니다.")
    if _last_shape != frame.shape:
        reset_motion()
        _last_shape = frame.shape
    try:
        results = model.predict(source=frame, conf=CONFIDENCE_THRESHOLD,
                                imgsz=config.VISION_IMAGE_SIZE, rect=False,
                                device="cpu", save=False, verbose=False)
        if results is None or len(results) == 0:
            reset_motion()
            return _result("NO_RESULT", "분석 결과가 반환되지 않았습니다.")
        result = results[0]
        candidates = {}
        h, w = frame.shape[:2]
        for box in result.boxes:
            confidence = float(box.conf[0])
            name = result.names[int(box.cls[0])].lower()
            kind = "smoke" if "smoke" in name else "fire" if "fire" in name or "flame" in name else None
            if kind is None or not np.isfinite(confidence) or confidence < CONFIDENCE_THRESHOLD:
                continue
            raw_coords = box.xyxy[0]
            if hasattr(raw_coords, "detach"):
                raw_coords = raw_coords.detach().cpu().numpy()
            coords = np.asarray(raw_coords, dtype=float)
            if len(coords) != 4 or not np.all(np.isfinite(coords)):
                raise ValueError("유효하지 않은 감지 좌표")
            x1, y1, x2, y2 = coords.astype(int)
            bbox = [max(0, min(w, x1)), max(0, min(h, y1)),
                    max(0, min(w, x2)), max(0, min(h, y2))]
            if kind not in candidates or confidence > candidates[kind][0]:
                candidates[kind] = (confidence, bbox)
    except Exception as exc:
        reset_motion()
        return _result("ANALYSIS_ERROR", f"로컬 모델 분석 오류: {exc}")

    for kind, analyzer in _motion_analyzers.items():
        if kind not in candidates:
            analyzer.reset()
            _previous_boxes.pop(kind, None)
    if not candidates:
        return _result("SAFE", "화재나 연기 후보가 감지되지 않았습니다.")

    observations = []
    try:
        for kind, (confidence, bbox) in candidates.items():
            analyzer = _motion_analyzers[kind]
            previous = _previous_boxes.get(kind)
            if previous is not None and _overlap(previous, bbox) < 0.2:
                analyzer.reset()
            motion = analyzer.analyze(frame, bbox, class_name=kind)
            _previous_boxes[kind] = bbox
            observations.append(dict(kind=kind, confidence=round(confidence, 4),
                box=bbox, status=motion.status, is_real_fire=motion.is_real_fire,
                is_real_smoke=motion.is_real_smoke, is_static_photo=motion.is_static_photo,
                consecutive_count=motion.consecutive_count,
                upward_ratio=motion.upward_ratio, turbulence_score=motion.turbulence_score))
    except Exception as exc:
        reset_motion()
        return _result("MOTION_ERROR", f"모션 검증 오류: {exc}")

    fire = next((o for o in observations if o["is_real_fire"]), None)
    smoke = next((o for o in observations if o["is_real_smoke"]), None)
    chosen = fire or smoke or max(observations, key=lambda o: (not o["is_static_photo"], o["confidence"]))
    shared = dict(confidence=chosen["confidence"], box=chosen["box"],
                  detected_classes=sorted(kind.upper() for kind in candidates), observations=observations)
    if fire:
        return _result("REAL_FIRE_FLICKERING", "불꽃 난류의 연속 모션 검증 완료",
                       fire_detected=True, is_real_fire=True, is_real_smoke=smoke is not None, **shared)
    if smoke:
        return _result("REAL_SMOKE_RISING", "상방 확산 연기 모션 검증 완료 (조기 감지)",
                       is_real_smoke=True, **shared)
    if config.SENSOR_MODE == "demo" and config.BYPASS_MOTION_FILTER:
        return _result("DEMO_BYPASS", "시연용 모션 검증 우회 (실제 검증 결과 아님)",
                       fire_detected=True, demo_bypass=True, **shared)
    blocked = all(o["is_static_photo"] for o in observations)
    return _result(chosen["status"], "사진/강체 움직임 차단" if blocked else "모션 검증 중",
                   is_static_photo=blocked, **shared)


def warmup():
    """Warm the model without preserving synthetic motion history."""
    try:
        return detect_fire(np.zeros((480, 640, 3), dtype=np.uint8))
    finally:
        reset_motion()
