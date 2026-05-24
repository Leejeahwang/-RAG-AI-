import sys
import os
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)
from gui.dashboard import init_tactical_engine
print("Testing init...")
qa, stt_model, pa, stream, tts_helper = init_tactical_engine()
if not qa:
    print("FAILED.")
