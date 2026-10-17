"""Stable integration entry point for capture snapshots and local detection."""
from vision import cctv_service, fire_detector


def frame_snapshot():
    return cctv_service.frame_snapshot()
