"""Isolated CPU/WAV benchmark. Run from the project root; see TTS_BENCHMARK.md."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
TEXTS = [
    "화재가 발생했습니다. 안전한 계단을 이용해 대피하십시오.",
    "연기가 들어오면 문을 닫고 젖은 수건으로 틈을 막으십시오. 현재 위치를 알리고 구조를 요청하십시오.",
    "아파트 입주자. 적용 범위 일. 화재 피난행동요령. 다른 세대나 복도에서 화재가 발생한 경우 대피 경로를 확인하십시오.",
]


def korean_voice(voices):
    for voice in voices:
        languages = [x.decode("utf-8", errors="ignore") if isinstance(x, bytes) else str(x)
                     for x in getattr(voice, "languages", [])]
        if "ko-kr" in voice.id.lower() or any(
            x.lstrip("\x00\x01\x02\x03\x04\x05").lower().replace("_", "-") in ("ko", "ko-kr")
            for x in languages
        ):
            return voice
    raise RuntimeError("Korean voice unavailable. Install a Korean OS/eSpeak voice first.")


def summarize(runs, texts):
    rows = []
    for index, text in enumerate(texts):
        attempts = [r for r in runs if r["text_index"] == index]
        good = [r for r in attempts if r["status"] == "ok"]
        row = {"text_index": index, "text": text, "attempts": len(attempts), "successes": len(good)}
        for field in ("wall_s", "cpu_s", "audio_s", "rtf"):
            row["median_" + field] = statistics.median(r[field] for r in good) if good else None
        rows.append(row)
    return rows


def pi_state():
    state = {}
    for command in ("measure_temp", "measure_clock arm", "get_throttled"):
        try:
            result = subprocess.run(["vcgencmd", *command.split()], capture_output=True,
                                    text=True, timeout=3, check=True)
            state[command] = result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            state[command] = None
    return state


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def worker(args):
    sys.path.insert(0, str(ROOT))
    # Use existing model caches; benchmark runs must not download Hugging Face models.
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      HF_HUB_DISABLE_TELEMETRY="1", NUMBA_CACHE_DIR=str(args.output / "numba_cache"))
    result = {"engine": args.worker, "status": "failed", "runs": [],
              "timing_scope": "text to complete WAV; no playback, queue or LLM",
              "thread_policy": "runtime defaults", "device": "cpu"}
    finished = threading.Event()
    sampler = None
    peak = 0
    try:
        import psutil
        import soundfile as sf
        process = psutil.Process()
        result["baseline_rss_bytes"] = peak = process.memory_info().rss

        def sample():
            nonlocal peak
            while not finished.wait(0.01):
                peak = max(peak, process.memory_info().rss)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        texts = json.loads((args.output / "texts.json").read_text(encoding="utf-8"))
        started = time.perf_counter()
        if args.worker == "ppaso":
            from voice.ppaso_wrapper import PpasoEngine
            engine = PpasoEngine(model_dir=str(args.ppaso_model_dir), device="cpu")
            if not engine.initialized:
                raise RuntimeError("PPASO initialization failed; check model files and dependencies")
            result["backend"] = "ONNX Runtime CPU"
            result["onnx_intra_op_threads"] = {
                k: s.get_session_options().intra_op_num_threads
                for k, s in engine.tts.backend.sessions.items()}

            def synthesize(text, path):
                if not engine.speak_to_file(text, str(path), speed=1.0):
                    raise RuntimeError("PPASO synthesis failed")

        elif args.worker == "melo":
            # Melo's g2p dependency may otherwise try to download NLTK data during timing.
            import nltk
            for name in ("corpora/cmudict", "taggers/averaged_perceptron_tagger"):
                nltk.data.find(name)
            from voice.melo_wrapper import MeloEngine
            engine = MeloEngine(device="cpu")
            if not engine.initialized or engine.get_model("ko") is None:
                raise RuntimeError("Melo initialization failed; prepare Korean model/BERT caches first")
            import torch
            result.update(backend="PyTorch CPU", torch_threads=torch.get_num_threads(),
                          pronunciation_note="Project wrapper substitutes MeCab on Windows; quality is not scored.")

            def synthesize(text, path):
                if not engine.speak_to_file(text, str(path), lang="ko", speed=1.0):
                    raise RuntimeError("Melo synthesis failed")

        else:
            if platform.system() not in ("Windows", "Linux"):
                raise RuntimeError("pyttsx3 benchmark currently supports Windows and Linux")
            import pyttsx3
            engine = pyttsx3.init("sapi5" if sys.platform == "win32" else "espeak")
            voice = korean_voice(engine.getProperty("voices"))
            engine.setProperty("voice", voice.id)
            engine.setProperty("rate", args.rate)
            engine.setProperty("volume", 1.0)
            result.update(backend="SAPI5" if sys.platform == "win32" else "eSpeak",
                          voice=voice.name, voice_id=voice.id, rate=args.rate)
            result["file_api"] = "private synchronous SAPI5 driver" if sys.platform == "win32" else "public save_to_file/runAndWait"

            def synthesize(text, path):
                if sys.platform == "win32":
                    # Repeated queued saves can hang in pyttsx3 2.99. Explicitly record this path.
                    engine.proxy._driver.save_to_file(text, str(path))
                else:
                    engine.save_to_file(text, str(path))
                    engine.runAndWait()

        result["initialization_s"] = time.perf_counter() - started
        result["rss_after_initialization_bytes"] = process.memory_info().rss
        started = time.perf_counter()
        synthesize(texts[0], args.output / "warmup.wav")
        result["first_synthesis_s"] = time.perf_counter() - started
        if sf.info(str(args.output / "warmup.wav")).duration <= 0:
            raise RuntimeError("Empty warmup WAV")
        result["rss_after_warmup_bytes"] = process.memory_info().rss
        for repeat in range(args.repeats):
            for index, text in enumerate(texts):
                path = args.output / f"text_{index + 1}_repeat_{repeat + 1}.wav"
                run = {"text_index": index, "repeat": repeat + 1, "status": "failed"}
                started, cpu_started = time.perf_counter(), time.process_time()
                try:
                    synthesize(text, path)
                    wall, cpu = time.perf_counter() - started, time.process_time() - cpu_started
                    duration = sf.info(str(path)).duration
                    if duration <= 0:
                        raise RuntimeError("Empty WAV")
                    run.update(status="ok", wall_s=wall, cpu_s=cpu, audio_s=duration,
                               rtf=wall / duration, file=path.name)
                except Exception as exc:
                    run["error"] = f"{type(exc).__name__}: {exc}"
                result["runs"].append(run)
                # Preserve completed samples even if a later synthesis times out.
                write_json(args.output / "result.json", result)
        result["status"] = "ok" if all(r["status"] == "ok" for r in result["runs"]) else "failed"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        finished.set()
        if sampler:
            sampler.join(timeout=1)
            peak = max(peak, process.memory_info().rss)
        result["peak_rss_bytes"] = peak or None
        result["peak_method"] = "RSS sampled every 10 ms (child process only)"
        if sys.platform.startswith("linux"):
            import resource
            result["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            result["peak_method"] = "Linux ru_maxrss (child process only)"
        result["versions"] = {}
        for name in ("psutil", "soundfile", "pyttsx3", "onnxruntime", "torch", "MeloTTS", "transformers"):
            try:
                result["versions"][name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                pass
        write_json(args.output / "result.json", result)
    return 0 if result["status"] == "ok" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engines", nargs="+", choices=("pyttsx3", "ppaso", "melo"),
                        default=["pyttsx3", "ppaso", "melo"])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=600, help="seconds per engine, including initialization")
    parser.add_argument("--text-file", type=Path, help="UTF-8, one test sentence per nonempty line")
    parser.add_argument("--output", type=Path, default=ROOT / "scratch" / "tts_benchmark" / datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    parser.add_argument("--ppaso-model-dir", type=Path, default=ROOT / "models" / "ppaso")
    parser.add_argument("--rate", type=int, default=190, help="pyttsx3 rate; neural engines use speed=1.0")
    parser.add_argument("--worker", choices=("pyttsx3", "ppaso", "melo"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeats < 1 or args.timeout <= 0 or args.rate < 1:
        parser.error("repeats, timeout and rate must be positive")
    args.output = args.output.resolve()
    args.ppaso_model_dir = args.ppaso_model_dir.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.worker:
        return worker(args)
    texts = [s.strip() for s in args.text_file.read_text(encoding="utf-8-sig").splitlines() if s.strip()] if args.text_file else TEXTS
    if not texts:
        parser.error("text-file is empty")
    import psutil
    report = {"environment": {"platform": platform.platform(), "machine": platform.machine(),
                              "python": sys.version, "cpu": platform.processor(),
                              "logical_cpus": os.cpu_count(), "ram_bytes": psutil.virtual_memory().total},
              "texts": texts, "repeats": args.repeats, "results": []}
    model_file = Path("/proc/device-tree/model")
    if sys.platform.startswith("linux") and model_file.exists():
        report["environment"]["board"] = model_file.read_text().rstrip("\x00")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    for name in dict.fromkeys(args.engines):
        directory = args.output / name
        directory.mkdir(exist_ok=True)
        if (directory / "result.json").exists():
            parser.error(f"output already contains {name} results; choose a new --output")
        write_json(directory / "texts.json", texts)
        before = pi_state()
        print(f"Measuring {name} ...", flush=True)
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", name,
                   "--output", str(directory), "--repeats", str(args.repeats),
                   "--ppaso-model-dir", str(args.ppaso_model_dir), "--rate", str(args.rate)]
        timed_out = False
        with (directory / "worker.log").open("w", encoding="utf-8") as log:
            try:
                completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                           stderr=subprocess.STDOUT, timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
        path = directory / "result.json"
        result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"engine": name, "status": "failed", "runs": []}
        if timed_out:
            result.update(status="timeout", error=f"Exceeded {args.timeout}s; memory peak unavailable")
            result["peak_rss_bytes"] = None
        elif completed.returncode != 0:
            result["status"] = "failed"
            result.setdefault("error", f"Worker exited {completed.returncode}; see worker.log")
        result.update(pi_before=before, pi_after=pi_state(), per_text=summarize(result["runs"], texts))
        write_json(path, result)
        report["results"].append(result)
        write_json(args.output / "comparison.json", report)
        print(f"{name}: {result['status']}", flush=True)
    fields = ["engine", "backend", "status", "initialization_s", "first_synthesis_s", "peak_rss_mib",
              "text_index", "text", "attempts", "successes", "median_wall_s", "median_cpu_s", "median_audio_s", "median_rtf"]
    with (args.output / "comparison.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in report["results"]:
            common = {k: result.get(k) for k in fields[:5]}
            common["peak_rss_mib"] = result["peak_rss_bytes"] / 2**20 if result.get("peak_rss_bytes") else None
            for row in result["per_text"]:
                writer.writerow({**common, **row})
    print(f"Results: {args.output}")
    return 0 if all(r["status"] == "ok" for r in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
