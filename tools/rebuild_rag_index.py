"""Back up the current corpus and rebuild FAISS, BM25 and metadata together."""
from pathlib import Path
from datetime import datetime
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("NUMBA_CACHE_DIR", str(ROOT / "scratch/numba_cache"))


def main():
    import config
    from rag.loader import load_and_split
    from rag.native_retriever import NativeRAGManager
    from sentence_transformers import SentenceTransformer

    chunks = load_and_split()
    sources = {doc.metadata.get("source") for doc in chunks}
    required = {f"zone_{zone}_layout.txt" for zone in "ABC"}
    if not required.issubset(sources):
        raise RuntimeError(f"Missing required documents: {sorted(required - sources)}")
    index_dir = Path(config.FAISS_INDEX_DIR)
    if index_dir.exists():
        backup = ROOT / "scratch/rag_index_backups" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        shutil.copytree(index_dir, backup)
        print(f"Backup: {backup}")
    manager = NativeRAGManager()
    manager.model = SentenceTransformer(manager.model_name, device="cpu")
    manager.build_index(chunks)
    print(f"Required zone documents verified; {len(chunks)} chunks indexed")


if __name__ == "__main__":
    main()
