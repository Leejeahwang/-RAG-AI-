import os
import sys
import platform

# Windows에서 심볼릭 링크 권한 에러(WinError 1314) 방지 (HuggingFace 관련)
if sys.platform == "win32":
    os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

import torch
import warnings
import time

# 경고 무시 (MeloTTS 내부에서 발생하는 특정 경고들)
warnings.filterwarnings("ignore", category=UserWarning)

# Windows 환경에서 MeCab/Fugashi/Eunjeon DLL 오류 방지를 위한 Mocking
if sys.platform == "win32":
    from unittest.mock import MagicMock
    
    # MeCab 관련 모킹
    mock_mecab = MagicMock()
    sys.modules["MeCab"] = mock_mecab
    sys.modules["mecab"] = mock_mecab
    
    # Fugashi (일본어용) 모킹
    sys.modules["fugashi"] = MagicMock()
    
    # Eunjeon (한국어용) 모킹 - g2pkk가 사용함
    import types
    import importlib.machinery
    
    mock_eunjeon = types.ModuleType("eunjeon")
    mock_eunjeon.__spec__ = importlib.machinery.ModuleSpec("eunjeon", None)
    
    # g2pkk는 eunjeon.Mecab 또는 eunjeon._mecab.Mecab을 찾음
    sys.modules["eunjeon"] = mock_eunjeon
    sys.modules["eunjeon._mecab"] = mock_eunjeon
    sys.modules["eunjeon.mecab"] = mock_eunjeon
    
    # g2pkk가 기대하는 클래스 구조 모킹
    class MockMecabClass:
        def __init__(self, *args, **kwargs): pass
        def pos(self, text): return [(text, 'NNG')] # 최소한의 형태소 결과 반환
        def morphs(self, text): return [text]
    
    mock_eunjeon.Mecab = MockMecabClass
    mock_mecab.Tagger = MockMecabClass

class MeloEngine:
    """
    MeloTTS를 위한 고품질 음성 합성 엔진 래퍼.
    최초 실행 시 모델을 로드하며, 싱글톤 패턴과 유사하게 한번 로드된 모델은 재사용합니다.
    """
    _instance = None
    _model_cache = {}

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MeloEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self, device=None):
        if not hasattr(self, 'initialized'):
            # 디바이스 설정 (CUDA 우선, 없으면 CPU)
            if device:
                self.device = device
            else:
                self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            
            print(f"[MeloTTS] 엔진 초기화 중 (Device: {self.device})...")
            
            try:
                from melo.api import TTS
                self.TTS = TTS
                self.initialized = True
            except ImportError:
                print("[MeloTTS] 오류: MeloTTS 라이브러리가 설치되어 있지 않습니다.")
                self.initialized = False

    def get_model(self, lang='ko'):
        """언어별 모델을 로드하거나 캐시에서 반환합니다."""
        if not self.initialized:
            return None
        
        # 언어 코드 정규화 (MeloTTS는 대문자 사용)
        melo_lang = lang.upper()
        if melo_lang == 'KO': melo_lang = 'KR' # MeloTTS 한국어 코드는 KR일 수 있음 확인 필요
        
        # 참고: MeloTTS 지원 코드 확인 (KR, EN, ZH, JP, ES, FR)
        if melo_lang not in self._model_cache:
            print(f"[MeloTTS] {melo_lang} 모델 로드 중...")
            start_t = time.time()
            try:
                # MeloTTS는 실제 언어 코드(KR, EN, JP 등)를 사용함
                self._model_cache[melo_lang] = self.TTS(language=melo_lang, device=self.device)
                print(f"[MeloTTS] {melo_lang} 모델 로드 완료 ({time.time() - start_t:.2f}s)")
            except Exception as e:
                print(f"[MeloTTS] {melo_lang} 모델 로드 실패: {e}")
                return None
        
        return self._model_cache[melo_lang]

    def speak_to_file(self, text, output_path, lang='ko', speed=1.0):
        """텍스트를 음성으로 변환하여 파일로 저장합니다."""
        model = self.get_model(lang)
        if not model:
            return False
        
        try:
            # MeloTTS 한국어 모델의 경우 speaker_ids['KR'] 사용
            melo_lang = lang.upper()
            if melo_lang == 'KO': melo_lang = 'KR'
            
            # HParams 객체를 딕셔너리로 변환하여 .get() 사용 가능하게 함
            speaker_ids = dict(model.hps.data.spk2id)
            # 해당 언어의 기본 화자 선택
            target_spk_id = speaker_ids.get(melo_lang, list(speaker_ids.values())[0])
            
            # quiet=True를 전달하여 'Text split to sentences' 및 tqdm 로그를 억제합니다.
            model.tts_to_file(text, target_spk_id, output_path, speed=speed, quiet=True)
            return True
        except Exception as e:
            print(f"[MeloTTS] 합성 중 오류 발생: {e}")
            return False

if __name__ == "__main__":
    # 테스트 코드
    engine = MeloEngine()
    if engine.initialized:
        test_text = "안녕하세요. 엣지 세이버 화재 감시 시스템입니다. 고품질 음성 합성 테스트 중입니다."
        test_file = "melo_test.wav"
        print(f"테스트 시작: {test_text}")
        if engine.speak_to_file(test_text, test_file, lang='ko'):
            print(f"성공: {test_file} 데이터가 생성되었습니다.")
        else:
            print("실패: 음성 합성 중 오류가 발생했습니다.")
    else:
        print("MeloTTS 엔진이 초기화되지 않았습니다.")
