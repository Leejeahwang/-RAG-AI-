"""Compare current retrieval and a LangChain/Chroma baseline on identical data.

Uses existing FAISS vectors/metadata, identical local query embeddings, CPU and
separate processes. Does not call an LLM or change the production index.
"""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import pickle
import platform
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
QUERIES = ["공장 화재시 대처방법은?", "아파트에서 화재가 발생하면 어떻게 대피하나요?",
           "A구역 화재시 대피방법은?", "사람이 숨을 안쉬는데 어떡해?"]
CASES = ("chroma", "native", "native_rerank")


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def worker(args):
    sys.path.insert(0, str(ROOT))
    os.environ["NUMBA_CACHE_DIR"] = str(args.output / "numba_cache")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", ANONYMIZED_TELEMETRY="False")
    import psutil
    process = psutil.Process()
    result = {"case": args.worker, "status": "failed", "queries": [], "runs": [],
              "baseline_rss_bytes": process.memory_info().rss}
    peak = result["baseline_rss_bytes"]
    stop = threading.Event()

    def sample():
        nonlocal peak
        while not stop.wait(.01):
            peak = max(peak, process.memory_info().rss)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    try:
        started = time.perf_counter()
        # Common imports, model and corpus in every process. Neural reranker is
        # loaded only in the explicitly labelled third case.
        import config
        import faiss
        from rag.native_retriever import NativeRAGManager
        config.USE_RERANKER = args.worker == "native_rerank"
        config.RERANKER_POLICY = args.reranker_policy
        manager = NativeRAGManager()
        manager.load_resources()
        if manager.index is None or not manager.metadata:
            raise RuntimeError("Existing FAISS corpus required")
        if args.worker == "native_rerank" and manager.reranker is None:
            raise RuntimeError("Requested BGE reranker did not load")
        result.update(corpus_count=len(manager.metadata), dimension=manager.index.d,
                      embedding=config.NATIVE_EMBEDDING_MODEL,
                      reranker=config.RERANKER_MODEL_NAME if config.USE_RERANKER else None,
                      top_k=config.RAG_TOP_K)
        result["reranker_policy"] = config.RERANKER_POLICY
        result["index_sha256"] = hashlib.sha256(Path(manager.index_file).read_bytes()).hexdigest()
        queries = QUERIES
        gold = None
        if args.quality:
            from rag_quality_dataset import CASES as quality_cases, gold_chunks, chunk_id
            queries = [item["query"] for item in quality_cases]
            gold = [gold_chunks(manager.metadata, item) for item in quality_cases]
            if any(not ids for ids in gold):
                raise RuntimeError(f"No evidence for cases: {[i + 1 for i, ids in enumerate(gold) if not ids]}")
            save(args.output / "quality_gold.json", [dict(item, gold_chunk_ids=ids) for item, ids in zip(quality_cases, gold)])
        result["model_and_index_load_s"] = time.perf_counter() - started
        if args.worker == "chroma":
            from langchain_core.embeddings import Embeddings
            from langchain_community.vectorstores import Chroma
            from chromadb.config import Settings

            class CommonEmbedding(Embeddings):
                def embed_query(self, text):
                    return manager.model.encode([text]).astype("float32")[0].tolist()

                def embed_documents(self, texts):
                    return manager.model.encode(texts).astype("float32").tolist()

            started = time.perf_counter()
            db = Chroma(collection_name="rag_benchmark", embedding_function=CommonEmbedding(),
                        persist_directory=str(args.output / "chroma_db"),
                        client_settings=Settings(anonymized_telemetry=False))
            vectors = manager.index.reconstruct_n(0, manager.index.ntotal)
            for offset in range(0, len(manager.metadata), 100):
                documents = manager.metadata[offset:offset + 100]
                # Feed existing vectors directly; no document re-embedding or downloads.
                db._collection.add(
                    ids=[str(i) for i in range(offset, offset + len(documents))],
                    documents=[d["page_content"] for d in documents],
                    metadatas=[{"source": d.get("source", "")} for d in documents],
                    embeddings=vectors[offset:offset + len(documents)].tolist())
            result["chroma_setup_s"] = time.perf_counter() - started

            def search(query):
                return [{"source": d.metadata.get("source", ""), "page_content": d.page_content}
                        for d in db.similarity_search(query, k=config.RAG_TOP_K)]
        else:
            search = manager.search
        result["rss_ready_bytes"] = process.memory_info().rss
        # Prepare each query once so lazy model setup is not part of warm timing.
        for query in (queries[:1] if args.quality else queries):
            search(query)
        print("Warmup complete", flush=True)
        for repeat in range(args.repeats):
            for index, query in enumerate(queries):
                started = time.perf_counter()
                documents = search(query)
                elapsed = time.perf_counter() - started
                result["runs"].append({"query_index": index, "repeat": repeat + 1,
                                       "wall_s": elapsed, "sources": [d.get("source", "") for d in documents]})
                if gold is not None:
                    rank = next((i + 1 for i, doc in enumerate(documents[:2]) if chunk_id(doc) in gold[index]), None)
                    result["runs"][-1].update(rank_at_2=rank, chunk_ids=[chunk_id(doc) for doc in documents[:2]])
                    result["runs"][-1]["rerank_status"] = manager.last_rerank_status
                    print(f"{index + 1}/{len(queries)} {'HIT' if rank else 'MISS'} {elapsed:.3f}s: {query}", flush=True)
            print(f"Repeat {repeat + 1}/{args.repeats} complete", flush=True)
        for index, query in enumerate(queries):
            runs = [r for r in result["runs"] if r["query_index"] == index]
            result["queries"].append({"query": query,
                                      "median_s": statistics.median(r["wall_s"] for r in runs),
                                      "min_s": min(r["wall_s"] for r in runs),
                                      "max_s": max(r["wall_s"] for r in runs),
                                      "sources": runs[-1]["sources"]})
            if gold is not None:
                ranks = [r["rank_at_2"] for r in runs]
                result["queries"][-1].update(category=quality_cases[index]["category"],
                    hit_at_1=all(rank == 1 for rank in ranks), hit_at_2=all(rank is not None for rank in ranks),
                    mrr_at_2=statistics.mean(1 / rank if rank else 0 for rank in ranks),
                    rank_at_2=ranks, gold_chunk_ids=gold[index], chunk_ids=runs[-1]["chunk_ids"])
        result["status"] = "ok"
    except Exception as exc:
        import traceback
        result["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        stop.set()
        thread.join(timeout=1)
        result["peak_rss_bytes"] = max(peak, process.memory_info().rss)
        result["memory_method"] = "10ms sampled process RSS; setup and query warmup included"
        if sys.platform.startswith("linux"):
            import resource
            result["peak_rss_bytes"] = max(result["peak_rss_bytes"], resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
            result["memory_method"] = "max of Linux ru_maxrss and sampled RSS"
        result["versions"] = {}
        for name in ("chromadb", "langchain-community", "sentence-transformers", "faiss-cpu", "torch", "transformers"):
            try:
                result["versions"][name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                pass
        save(args.output / "result.json", result)
    return 0 if result["status"] == "ok" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--output", type=Path, default=ROOT / "scratch/rag_benchmark" / datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    parser.add_argument("--worker", choices=CASES, help=argparse.SUPPRESS)
    parser.add_argument("--quality", action="store_true", help="Compare 28 fixed evidence retrieval cases; first query warms the model")
    parser.add_argument("--reranker-policy", choices=("full", "selective"), default="full")
    args = parser.parse_args()
    if args.repeats < 1 or args.timeout <= 0:
        parser.error("repeats and timeout must be positive")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.worker:
        return worker(args)
    report = {"environment": {"platform": platform.platform(), "python": sys.version,
                              "logical_cpus": os.cpu_count(), "cpu": platform.processor()},
              "repeats": args.repeats,
              "quality": args.quality,
              "scope": "warm query embedding + retrieval; LLM/TTS excluded; same vectors and corpus; not an exact old-project replay",
              "results": []}
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1", ANONYMIZED_TELEMETRY="False")
    for case in dict.fromkeys(args.cases):
        output = args.output / case
        output.mkdir()
        print(f"Measuring {case} ...", flush=True)
        with (output / "worker.log").open("w", encoding="utf-8") as log:
            try:
                subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", case,
                                "--output", str(output), "--repeats", str(args.repeats),
                                "--reranker-policy", args.reranker_policy] + (["--quality"] if args.quality else []),
                               cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                               timeout=args.timeout)
            except subprocess.TimeoutExpired:
                save(output / "result.json", {"case": case, "status": "timeout", "queries": []})
        path = output / "result.json"
        result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"case": case, "status": "failed", "queries": []}
        report["results"].append(result)
        save(args.output / "comparison.json", report)
        print(f"{case}: {result['status']}", flush=True)
    with (args.output / "comparison.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["case", "query", "median_s", "min_s", "max_s", "peak_rss_mib", "sources"])
        writer.writeheader()
        for result in report["results"]:
            for row in result["queries"]:
                writer.writerow({"case": result["case"], **{key: row[key] for key in ("query", "median_s", "min_s", "max_s", "sources")},
                                 "peak_rss_mib": result["peak_rss_bytes"] / 2**20})
    print(f"Results: {args.output}")
    return 0 if all(r["status"] == "ok" for r in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
