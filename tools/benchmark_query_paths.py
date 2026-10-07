"""Measure the real _process_query methods with real RAG and controlled outputs.

Only the method body is loaded to avoid starting hardware, cameras or alarms.
LLM and audio output are stubs: this is not an end-to-end live app benchmark.
"""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("NUMBA_CACHE_DIR", str(ROOT / "scratch/numba_cache"))
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")


class AudioStub:
    def speak_async(self, text, **kwargs):
        self.spoken = text

    def wait_until_idle(self, **kwargs):
        return True


def load_query_method(filename, namespace):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8-sig"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_process_query")
    code = ast.Module(body=[method], type_ignores=[])
    exec(compile(ast.fix_missing_locations(code), filename, "exec"), namespace)
    return namespace["_process_query"]


def main():
    import config
    from rag.native_retriever import rag_manager
    config.USE_RERANKER = True
    rag_manager.load_resources()
    if rag_manager.reranker is None:
        raise RuntimeError("BGE required for this comparison")
    queries = ["사람이 숨을 안쉬는데 어떡해?", "피가 멈추지 않고 철철 흘러 지혈 어떻게 하지?",
               "공장 불이 다른 작업 구역으로 번지는데 방화문 어떻게 해?",
               "아파트 화재 때 엘리베이터 타도 돼?"]
    methods = {filename: load_query_method(filename, dict(time=time, config=config, rag_manager=rag_manager))
               for filename in ("main.py", "main_test.py")}
    rows = []
    contexts = []

    def answer_stub(context, query, **kwargs):
        contexts.append(dict(query=query, context=context, cloud_context=kwargs.get("cloud_context")))
        return SimpleNamespace(provider="controlled_stub", text="측정용 고정 응답")

    with patch("rag.provider.generate_guidance", side_effect=answer_stub):
        for filename, method in methods.items():
            app = SimpleNamespace(current_level=0, tts=AudioStub())
            for policy in ("full", "selective"):
                config.RERANKER_POLICY = policy
                with contextlib.redirect_stdout(io.StringIO()):
                    method(app, queries[0], "ko")
                for repeat in range(2):
                    for query in queries:
                        output = io.StringIO()
                        started = time.perf_counter()
                        with contextlib.redirect_stdout(output):
                            method(app, query, "ko")
                        rows.append(dict(file=filename, policy=policy, query=query, repeat=repeat + 1,
                                         method_wall_s=time.perf_counter() - started,
                                         timings=app.last_query_timings.copy(),
                                         rerank_status=rag_manager.last_rerank_status,
                                         provider_context=contexts[-1], log=output.getvalue()))
                        assert app.tts.spoken == "측정용 고정 응답"
                        assert "[답변 생성 오류]" not in output.getvalue()
                        print(f"{filename} {policy} {repeat+1}: {app.last_query_timings['rag_s']:.3f}s {query}", flush=True)
    summary = []
    for filename in methods:
        for policy in ("full", "selective"):
            for query in queries:
                runs = [row for row in rows if row["file"] == filename and row["policy"] == policy and row["query"] == query]
                summary.append(dict(file=filename, policy=policy, query=query,
                                    rag_median_s=statistics.median(row["timings"]["rag_s"] for row in runs),
                                    method_median_s=statistics.median(row["method_wall_s"] for row in runs)))
    output = ROOT / "scratch/query_paths_benchmark.json"
    output.write_text(json.dumps(dict(scope=__doc__, summary=summary, runs=rows), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Results: {output}")


if __name__ == "__main__":
    main()
