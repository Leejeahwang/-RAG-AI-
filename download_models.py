"""현재 앱의 PPASO 파일 및 RAG 모델 캐시 준비. import 시 다운로드하지 않습니다."""
import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PPASO_REPO = "akamotaco/ppaso-tts-v1"
PPASO_FILES = (
    "config.json", "example/ppaso_tts.py",
    "runtime/data/g2p_mfa.py", "runtime/data/phoneme_mfa.py",
    "runtime/data/ko_normalize.py", "runtime/dict/korean_mfa.dict",
    "onnx/text_encoder.onnx", "onnx/variance.onnx",
    "onnx/acoustic.onnx", "onnx/vocoder.onnx",
    "onnx/text_encoder.onnx.data", "onnx/variance.onnx.data",
    "onnx/acoustic.onnx.data", "onnx/vocoder.onnx.data",
)


def check_ppaso(directory):
    missing = [name for name in PPASO_FILES
               if not (directory / name).is_file() or (directory / name).stat().st_size == 0]
    for name in missing:
        print(f"Missing: {directory / name}")
    print("PPASO files: " + ("missing" if missing else "ok"))
    return not missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("ppaso", "rag", "all"), default="all")
    parser.add_argument("--check", action="store_true", help="네트워크 없이 파일/RAG 모델 로드 확인")
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.check:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import config
    directory = Path(config.PPASO_MODEL_DIR).resolve()
    ok = True
    if args.target in ("ppaso", "all"):
        if not args.check:
            from huggingface_hub import snapshot_download
            snapshot_download(PPASO_REPO, local_dir=str(directory),
                              allow_patterns=["config.json", "example/**", "runtime/**", "onnx/**"])
        ok = check_ppaso(directory) and ok
    if args.target in ("rag", "all"):
        from sentence_transformers import SentenceTransformer, CrossEncoder
        models = [(SentenceTransformer, config.NATIVE_EMBEDDING_MODEL)]
        if config.USE_RERANKER:
            models.append((CrossEncoder, config.RERANKER_MODEL_NAME))
        for cls, name in models:
            try:
                model = cls(name, device="cpu", local_files_only=args.check)
                print(f"RAG model ready: {name}")
                del model
            except Exception as exc:
                print(f"RAG model failed: {name}: {type(exc).__name__}: {exc}")
                ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
