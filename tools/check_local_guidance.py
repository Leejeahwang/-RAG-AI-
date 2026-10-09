"""Run actual local RAG + Ollama and synthesize the answer without playback."""
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['AI_PROVIDER']='local'


def main():
    from rag.native_retriever import rag_manager
    from rag.context import build_manual_context
    from rag.provider import generate_guidance
    from voice.ppaso_wrapper import PpasoEngine
    question='공장 화재시 대처방법은?'
    rag_manager.load_resources()
    started=time.perf_counter()
    docs=rag_manager.search(question)
    searched=time.perf_counter()
    result=generate_guidance(build_manual_context(docs),question)
    generated=time.perf_counter()
    assert result.provider=='ollama' and result.text.strip()
    wav=ROOT/'scratch/local_guidance.wav'
    engine=PpasoEngine()
    assert engine.initialized and engine.speak_to_file(result.text,str(wav))
    report={'question':question,'provider':result.provider,'text':result.text,
            'sources':[d.get('source') for d in docs],'search_s':searched-started,
            'answer_s':generated-searched,'tts_s':time.perf_counter()-generated,
            'wav':str(wav),'speaker_tested':False}
    (ROOT/'scratch/local_guidance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
