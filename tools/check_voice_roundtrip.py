"""Offline WAV -> STT check; does not record a microphone or play audio."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='small')
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'scratch/voice_roundtrip.json')
    args = parser.parse_args()
    os.environ['STT_WHISPER_MODEL'] = args.model
    os.environ['STT_LOCAL_FILES_ONLY'] = 'true'
    import soundfile as sf
    import numpy as np
    from scipy.signal import resample_poly
    from voice import stt
    started = time.perf_counter()
    model = stt._load_model()
    if model is None:
        return 1
    loaded = time.perf_counter()
    samples, sr = sf.read(args.audio, dtype='float32')
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    samples = resample_poly(samples, 16000, sr).astype(np.float32)
    text, lang = stt._transcribe(model, samples)
    report = {'model':args.model,'text':text,'language':lang,'model_load_s':loaded-started,
              'transcription_s':time.perf_counter()-loaded,'microphone_tested':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if text else 1


if __name__ == '__main__':
    raise SystemExit(main())
