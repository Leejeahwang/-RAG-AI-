"""Bounded local vision-model/camera check on Windows or Raspberry Pi.

No cloud requests, siren, speech, or saved camera images. Timings describe this
host and these frames only; live smoke/flame accuracy requires labelled trials.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import statistics
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config
import numpy as np
from vision import cctv_service, fire_detector


def timings(samples):
    if not samples:
        return None
    return dict(samples=len(samples), mean_ms=statistics.mean(samples),
                p50_ms=float(np.percentile(samples, 50)), p95_ms=float(np.percentile(samples, 95)))


def camera_check(seconds, count):
    cctv_service.camera_running = True
    thread = threading.Thread(target=cctv_service.camera_worker_thread, daemon=True)
    thread.start()
    started = time.monotonic()
    seen = None
    samples, ages, statuses = [], [], Counter()
    try:
        while len(samples) < count and time.monotonic()-started < seconds:
            if not thread.is_alive():
                break
            frame, acquired, sequence, offline = cctv_service.frame_snapshot()
            age = time.monotonic()-acquired
            if not offline and frame is not None and sequence != seen and age <= config.FRAME_MAX_AGE:
                seen = sequence
                before = time.perf_counter()
                result = fire_detector.detect_fire(frame)
                samples.append((time.perf_counter()-before)*1000)
                ages.append(age*1000)
                statuses[result['status']] += 1
            else:
                time.sleep(.01)
    finally:
        cctv_service.camera_running = False
        thread.join(timeout=1)
        fire_detector.reset_motion()
    errors = {'ANALYSIS_ERROR', 'MOTION_ERROR', 'MODEL_NOT_INITIALIZED', 'INVALID_INPUT', 'NO_RESULT'}
    complete = len(samples) == count and not errors.intersection(statuses)
    return dict(status='passed' if complete else 'incomplete', frames=len(samples),
                requested_frames=count, elapsed_s=time.monotonic()-started,
                inference=timings(samples), frame_age=timings(ages), statuses=dict(statuses),
                accuracy='not_tested: no labelled smoke/flame stimuli')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', action='store_true', help='Open the local camera; save metrics only.')
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--frames', type=int, default=10)
    parser.add_argument('--output', type=Path, default=ROOT/'scratch'/'vision_runtime.json')
    args = parser.parse_args()
    if not 0 < args.seconds <= 300 or not 1 <= args.frames <= 1000:
        parser.error('seconds must be 0..300 and frames 1..1000')
    versions = {}
    for package in ('numpy', 'opencv-python', 'ultralytics', 'ncnn', 'onnxruntime', 'torch'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    device = Path('/proc/device-tree/model')
    board = device.read_text().strip('\x00') if platform.system() == 'Linux' and device.exists() else None
    model_path = Path(fire_detector.loaded_model_path) if fire_detector.loaded_model_path else None
    model_files = {}
    if model_path and model_path.is_dir():
        for name in ('model.ncnn.param', 'model.ncnn.bin', 'metadata.yaml', 'export_manifest.json'):
            path = model_path/name
            model_files[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    report = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  host=dict(os=platform.system(), machine=platform.machine(), python=platform.python_version(),
                            processor=platform.processor(), board=board), packages=versions,
                  model=str(model_path), model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest()
                        if model_path and model_path.is_file() else None,
                  model_files_sha256=model_files,
                  requested_model=config.VISION_MODEL_PATH,
                  input_size=[config.VISION_IMAGE_SIZE, config.VISION_IMAGE_SIZE],
                  device='cpu', rect=False,
                  bypass_motion_filter=config.BYPASS_MOTION_FILTER,
                  physical_smoke_flame='not_tested',
                  raspberry_pi='running_on_target' if board and 'Raspberry Pi' in board else 'not_available_on_this_host')
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    started = time.perf_counter()
    warmup = fire_detector.warmup()
    report['warmup_ms'] = (time.perf_counter()-started)*1000
    statuses, samples = Counter(), []
    for _ in range(args.frames):
        started = time.perf_counter()
        result = fire_detector.detect_fire(frame)
        samples.append((time.perf_counter()-started)*1000)
        statuses[result['status']] += 1
    report['blank_frames'] = dict(status='passed' if set(statuses) == {'SAFE'} else 'failed',
                                  statuses=dict(statuses), inference=timings(samples),
                                  warmup_status=warmup['status'])
    fire_detector.reset_motion()
    report['camera'] = camera_check(args.seconds, args.frames) if args.camera else dict(status='not_requested')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['blank_frames']['status'] == 'passed' and (
        not args.camera or report['camera']['status'] == 'passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
