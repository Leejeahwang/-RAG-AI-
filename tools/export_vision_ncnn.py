"""Export the project's fire/smoke checkpoint to NCNN FP32 at 640x640.

No model downloads, camera, cloud, or audio. Existing artifacts are not overwritten.
Staging files remain under ignored scratch/ for export diagnostics.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'vision/models/fire_smoke.pt')
    parser.add_argument('--output', type=Path, default=ROOT/'vision/models/fire_smoke_ncnn_model')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if not source.is_file() or source.suffix != '.pt':
        parser.error(f'Existing local .pt checkpoint required: {source}')
    if output.exists():
        parser.error(f'Output already exists; use a new output directory: {output}')
    if not output.name.endswith('_ncnn_model'):
        parser.error('Output directory name must end with _ncnn_model for Ultralytics loading')
    missing = [name for name in ('ultralytics', 'ncnn', 'pnnx') if importlib.util.find_spec(name) is None]
    if missing:
        parser.error('Install requirements_vision_export.txt; missing: ' + ', '.join(missing))

    import numpy as np
    from ultralytics import YOLO

    stage = ROOT/'scratch'/f'vision_ncnn_export_{uuid.uuid4().hex}'
    stage.mkdir(parents=True)
    staged_source = stage/'fire_smoke.pt'
    shutil.copy2(source, staged_source)
    model = YOLO(str(staged_source), task='detect')
    if model.names != {0: 'fire', 1: 'smoke'}:
        parser.error(f'Expected fire/smoke classes; checkpoint has {model.names}')
    exported = Path(model.export(format='ncnn', imgsz=config.VISION_IMAGE_SIZE,
                                 batch=1, half=False, device='cpu'))
    files = ('model.ncnn.param', 'model.ncnn.bin', 'metadata.yaml')
    if any(not (exported/name).is_file() or (exported/name).stat().st_size == 0 for name in files):
        raise RuntimeError(f'NCNN export incomplete: {exported}')
    # Exercise the actual exported runtime before making it the deployed artifact.
    probe = YOLO(str(exported), task='detect')
    result = probe.predict(np.zeros((640, 640, 3), dtype=np.uint8),
                           imgsz=config.VISION_IMAGE_SIZE, rect=False, device='cpu',
                           conf=.35, verbose=False, save=False)[0]
    if probe.names != model.names or len(result.boxes):
        raise RuntimeError('Exported model class/blank-frame sanity check failed')
    manifest = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                    source_name=source.name, source_sha256=sha256(source),
                    format='ncnn', precision='fp32', imgsz=[640, 640], batch=1,
                    classes=model.names, architecture=getattr(model.model, 'yaml', {}).get('yaml_file'),
                    packages={name: importlib.metadata.version(name)
                              for name in ('ultralytics', 'torch', 'ncnn', 'pnnx')},
                    files={name: sha256(exported/name) for name in files},
                    blank_frame_check='passed', detection_accuracy='not_evaluated',
                    raspberry_pi_performance='not_measured')
    output.mkdir(parents=True)
    for name in files:
        shutil.copy2(exported/name, output/name)
    (output/'export_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'NCNN FP32 640x640 ready: {output}')
    print(f'Source SHA-256: {manifest["source_sha256"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
