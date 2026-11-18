"""Real model/index/TTS smoke check with synthetic camera and silent SDL output."""
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['SDL_AUDIODRIVER']='dummy'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['AI_PROVIDER']='local'


def main():
    import numpy as np
    import main as application
    from vision import cctv_service
    import config
    app=application.EdgeSaver()
    def synthetic_camera():
        while cctv_service.camera_running:
            cctv_service.latest_frame = np.zeros((480,640,3),dtype=np.uint8)
            time.sleep(0.1)
    started=time.perf_counter()
    try:
        with patch.object(cctv_service,'camera_worker_thread',synthetic_camera), \
             patch.object(config,'AI_PROVIDER','local'), \
             patch.object(config,'OLLAMA_EMERGENCY_TIMEOUT',2):
            app.initialize()
            initialized=time.perf_counter()
            deadline=time.monotonic()+15
            while 'CAM:SAFE' not in app.current_risk_stats and time.monotonic()<deadline:
                time.sleep(0.1)
            assert 'CAM:SAFE' in app.current_risk_stats, app.current_risk_stats
            app._alarm_hold_until = time.monotonic()+30
            app._trigger_rag_alert('[공장 A구역] 화재 대피 방법','synthetic integration smoke','A')
            deadline=time.monotonic()+20
            while app._jobs.unfinished_tasks and time.monotonic()<deadline:
                time.sleep(0.1)
            assert app._jobs.unfinished_tasks==0, 'guidance job timed out'
            assert app.tts.wait_until_idle(timeout=20), 'speech timed out'
            assert not app.tts.last_error, app.tts.last_error
            report={'status':'ok','initialization_s':initialized-started,
                    'tts_engine':app.tts._engine_type,'guidance':app._cached_evac_guidance,
                    'risk_stats':app.current_risk_stats,'physical_camera_tested':False,
                    'physical_speaker_tested':False}
            (ROOT/'scratch/integration_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        app.cleanup()


if __name__=='__main__':
    main()
