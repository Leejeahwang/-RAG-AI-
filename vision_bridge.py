"""Integration compatibility for unchanged upstream vision sources.

Frame age is measured from first observation here, not camera acquisition.
The original camera module does not publish acquisition timestamps.
"""
import importlib.util
import sys
import threading
import time

import config
from vision import fire_detector


def _load_camera_service():
    name = "vision.cctv_service"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.find_spec(name)
    module = importlib.util.module_from_spec(spec)
    # Original source refers to sys without importing it on Windows.
    module.sys = sys
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


cctv_service = _load_camera_service()
_lock = threading.Lock()
_observed_frame = None
_observed_at = 0.0
_frame_id = 0


def frame_snapshot():
    global _observed_frame, _observed_at, _frame_id
    with _lock:
        frame = cctv_service.latest_frame
        if frame is not _observed_frame:
            _observed_frame = frame
            _observed_at = time.monotonic()
            _frame_id += 1
        return frame, _observed_at, _frame_id, cctv_service.camera_offline
