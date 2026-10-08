import os
import sys
import time
import logging

_LOGGER = logging.getLogger(__name__)

class PpasoEngine:
    """
    PpasoEngine: Ppaso-TTS (한국어 초경량 온디바이스 음성 합성) 래퍼.
    ======================================================================
    - ONNXRuntime 기반 단일 여성 화자 한국어 음성 합성
    - 싱글톤 패턴으로 모델을 메모리에 1회만 로드하여 재사용
    - 22050Hz 모노 WAV 파일 출력
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PpasoEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self, model_dir=None, device="cpu"):
        if not hasattr(self, 'initialized'):
            self.initialized = False
            self.tts = None

            # 1. 모델 경로 확인
            if model_dir is None:
                try:
                    import config
                    model_dir = getattr(config, 'PPASO_MODEL_DIR', 'models/ppaso')
                except Exception:
                    model_dir = 'models/ppaso'

            base_dir = os.path.abspath(model_dir)
            example_dir = os.path.join(base_dir, "example")

            if not os.path.exists(base_dir):
                print(f"[PpasoTTS] 오류: 모델 디렉토리를 찾을 수 없음: {base_dir}")
                return

            # 2. sys.path에 런타임 및 예제 폴더 등록
            if base_dir not in sys.path:
                sys.path.insert(0, base_dir)
            if example_dir not in sys.path:
                sys.path.insert(0, example_dir)

            # 3. PpasoTTS 로드
            try:
                import soundfile as sf
                self.sf = sf
                from ppaso_tts import PpasoTTS

                print(f"[PpasoTTS] 모델 초기화 중 (Device: {device}, Dir: {base_dir})...")
                start_t = time.time()
                self.tts = PpasoTTS(model_dir=base_dir, backend='onnx', device=device)
                self.sample_rate = 22050
                self.initialized = True
                print(f"[PpasoTTS] 초기화 완료 ({time.time() - start_t:.2f}s)")
            except Exception as e:
                print(f"[PpasoTTS] 초기화 실패: {e}")
                self.initialized = False

    def speak_to_file(self, text: str, output_path: str, lang: str = 'ko', speed: float = 1.0) -> bool:
        """
        텍스트를 음성으로 변환하여 지정된 파일 경로에 WAV로 저장합니다.
        MeloEngine의 speak_to_file과 동일한 인터페이스를 유지합니다.
        """
        if not self.initialized or self.tts is None:
            _LOGGER.warning("[PpasoTTS] 엔진이 초기화되지 않았습니다.")
            return False

        if not text or not text.strip():
            return False

        try:
            wav = self.tts.synthesize(text.strip(), chunked=True)
            if wav is None or len(wav) == 0:
                return False

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

            # 발화 속도(speed) 조정 (속도 변경 요청 시 sample_rate 스케일링)
            target_sr = self.sample_rate
            if isinstance(speed, (int, float)) and 0.5 <= speed <= 2.0 and speed != 1.0:
                target_sr = int(self.sample_rate * speed)

            self.sf.write(output_path, wav, target_sr)
            return True
        except Exception as e:
            _LOGGER.error(f"[PpasoTTS] 음성 합성 중 오류: {e}")
            return False

if __name__ == "__main__":
    engine = PpasoEngine()
    if engine.initialized:
        test_path = "scratch/ppaso_wrapper_test.wav"
        ok = engine.speak_to_file("안녕하세요. 빠소 엔진 래퍼 테스트 중입니다.", test_path)
        print("합성 결과:", "성공" if ok else "실패", test_path)
    else:
        print("초기화 실패")
