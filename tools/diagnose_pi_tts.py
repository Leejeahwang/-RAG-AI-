"""Run one TTS diagnostic stage in either integration or feature/RAG checkout.

inspect and synth do not play audio. play and project produce audible output.
Run each stage as a separate process to isolate native audio/model failures.
"""
import argparse
import importlib.metadata
import logging
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TEXT = "한국어 음성 출력 시험입니다. 안전한 계단으로 대피하십시오."


def inspect():
    import config
    print("platform:", platform.platform())
    print("python:", sys.executable)
    print("cwd:", Path.cwd())
    print("configured_engine:", config.TTS_ENGINE)
    model = Path(getattr(config, "PPASO_MODEL_DIR", "models/ppaso")).resolve()
    print("ppaso_model_dir:", model, "exists:", model.exists())
    for name in ("pygame", "pyttsx3", "onnxruntime", "soundfile", "python-mecab-ko"):
        try:
            print("package:", name, importlib.metadata.version(name))
        except importlib.metadata.PackageNotFoundError:
            print("package:", name, "NOT INSTALLED")
    for name in ("espeak", "espeak-ng", "aplay", "pactl", "wpctl"):
        print("command:", name, shutil.which(name))
    # Only audio/session fields, never dotenv contents or API credentials.
    for name in ("SDL_AUDIODRIVER", "SDL_AUDIO_DEVICE_NAME", "AUDIODEV",
                 "XDG_RUNTIME_DIR", "PULSE_SERVER"):
        print("environment:", name, os.getenv(name, "<unset>"))
    import pygame
    try:
        from pygame._sdl2 import audio
        pygame.mixer.init()
        print("SDL playback devices:", audio.get_audio_device_names(False))
    except Exception as exc:
        print("SDL device enumeration failed:", type(exc).__name__, str(exc))
    finally:
        pygame.quit()


def synth(path):
    import config  # Load the checkout's config before the wrapper.
    from voice.ppaso_wrapper import PpasoEngine
    engine = PpasoEngine()
    print("ppaso_initialized:", engine.initialized, flush=True)
    if not engine.initialized:
        raise RuntimeError("PPASO initialization failed; see preceding model/dependency error")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not engine.speak_to_file(TEXT, str(path), lang="ko", speed=1.0):
        raise RuntimeError("PPASO synthesis failed")
    with wave.open(str(path), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
        duration = wav.getnframes() / wav.getframerate()
        print("wav:", path, "duration_s:", round(duration, 2),
              "rate:", wav.getframerate(), "channels:", wav.getnchannels())
        if not duration or not frames or not any(frames):
            raise RuntimeError("WAV is empty or contains only zeros")
    print("SYNTH OK: nonempty WAV. This does not confirm audible playback.")


def play(path):
    import pygame
    try:
        pygame.mixer.init()
        print("mixer:", pygame.mixer.get_init(), flush=True)
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        deadline = time.monotonic() + 60
        while pygame.mixer.music.get_busy():
            if time.monotonic() >= deadline:
                raise TimeoutError("pygame playback exceeded 60 seconds")
            time.sleep(0.05)
        print("PLAY OK: pygame finished. Confirm whether sound was heard.")
    finally:
        pygame.mixer.quit()


def project():
    from voice.tts import TTSHelper
    tts = TTSHelper()
    try:
        print("actual_engine:", getattr(tts, "_engine_type", "unknown"), flush=True)
        tts.speak_async(TEXT, lang="ko", speed=1.0)
        if not tts.wait_until_idle(timeout=120):
            raise TimeoutError("Project TTS did not finish within 120 seconds")
        error = getattr(tts, "last_error", "")
        if error:
            raise RuntimeError(error)
        print("QUEUE FINISHED: confirm sound and inspect TTS error logs above.")
        print("feature/RAG can drain its queue after synthesis failure; this alone is not success.")
    finally:
        if hasattr(tts, "close"):
            tts.close()
        else:
            tts.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("inspect", "synth", "play", "project"), required=True)
    parser.add_argument("--wav", type=Path, default=ROOT / "scratch/pi_tts_probe.wav")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print("stage:", args.stage, flush=True)
    try:
        if args.stage in ("synth", "play"):
            globals()[args.stage](args.wav.resolve())
        else:
            globals()[args.stage]()
    except Exception:
        logging.exception("TTS DIAGNOSTIC FAILED")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
