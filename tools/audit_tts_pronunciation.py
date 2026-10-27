"""Audit local manual notation and optionally synthesize offline A/B clips.

python tools/audit_tts_pronunciation.py [--audio]
Outputs stay in output/tts_pronunciation; no API or microphone is used.
"""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from voice.pronunciation import local_pronunciation

CASES = [
    'CO2 소화기를 확인하십시오.', 'CO₂ 소화기', 'N2 가스', 'H2O',
    '15m 직진하십시오.', '1.5 m 이하', '0.5 m', '5cm', '9.8kg',
    '33㎡', '2㎥', '75℃', '80%', '-5도', '10~15m', '3~5분',
    'ABC 분말 소화기', 'BC 분말 소화기', 'D급 소화기', 'A3 기둥',
    'CPR', 'GPS', 'E-STOP', 'E/V홀', '119에 신고하십시오.',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', action='store_true', help='Generate six raw/corrected PPASO clip pairs offline')
    args = parser.parse_args()
    target = ROOT / 'output' / 'tts_pronunciation'
    target.mkdir(parents=True, exist_ok=True)
    corpus = [(str(path.relative_to(ROOT)), path.read_text(encoding='utf-8', errors='replace'))
              for path in sorted((ROOT/'data').rglob('*.txt'))]
    chunks = ROOT/'data'/'chunked_manuals.json'
    if chunks.is_file():
        corpus.extend((f'data/chunked_manuals.json[{i}]', chunk.get('content', ''))
                      for i, chunk in enumerate(json.loads(chunks.read_text(encoding='utf-8'))))
    counts = Counter(token for _, text in corpus for token in re.findall(
        r'(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9/²³₂₃-]{0,17}(?![A-Za-z0-9_])', text))
    spec = importlib.util.spec_from_file_location('ppaso_normalizer', ROOT/'models/ppaso/runtime/data/ko_normalize.py')
    normalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(normalizer)
    lines = ['# PPASO 발음 점검', '',
             '로컬 매뉴얼 TXT와 검색용 JSON을 점검했습니다. 원문/청크 중복이 있으므로 출현 수는 고유 문서 수가 아닙니다.',
             '아래는 모델 전처리의 문자 변환 결과입니다. 실제 음성을 청취하여 오류를 확정한 결과는 아닙니다.',
             '단위·부호 보존은 공통 음성 전처리, 화학식·약어·소수 읽기는 로컬 음성 경로에 적용합니다.', '',
             '| 입력 예시 | 기존 PPASO 정규화 | 교정 후 PPASO 정규화 |', '|---|---|---|']
    for text in CASES:
        # The baseline bypasses application cleanup to isolate model normalization.
        lines.append(f'| {text} | {normalizer.normalize_korean_text(text)} | {normalizer.normalize_korean_text(local_pronunciation(text))} |')
    lines += ['', '## 매뉴얼의 영문·숫자 혼합 표기', '', '| 표기 | 출현 수 |', '|---|---|']
    lines.extend(f'| {token} | {count} |' for token, count in counts.most_common(60))
    lines += ['', '## 별도 청취·원문 검토 대상', '',
              '- A3, KFSC101: 위치·규격 식별자. 임의로 숫자를 수량으로 바꾸지 않습니다.',
              '- A/B/C/D급, ABC/BC: 등급·약어. 한글 치환 후에도 청취로 명료도를 확인해야 합니다.',
              '- 하향식피난구, 경량칸막이, 양압식 공기호흡기, 유증기: 긴 전문어는 실제 청취로 확인합니다.',
              '- 시각(14:00), 비율(30:2), 분수, 수식, 미등록 화학식·복합 단위는 자동 의미 변환하지 않습니다.',
              '- 숫자+시간·명·개는 한자어/고유어 읽기가 문맥에 따라 달라 일괄 변환하지 않습니다.',
              '- 일부 PDF 추출문에 제어문자·HTML 잔재가 있습니다. 발음 사전으로 내용을 추정하지 말고 원본 문서를 확인해야 합니다.',
              '- 비교 음성의 raw는 공통 정리 없이 PPASO에 직접 넣은 결과이며, fixed는 교정 후 결과입니다.',
              '- 119는 앱 공통 전처리에서 이미 일일구로 처리합니다. 아래 raw 직접 합성과 구분하세요.', '']
    (target/'audit.md').write_text('\n'.join(lines), encoding='utf-8')
    if args.audio:
        from voice.ppaso_wrapper import PpasoEngine
        engine = PpasoEngine()
        if not engine.initialized:
            raise RuntimeError('PPASO 초기화 실패')
        samples = [CASES[0], CASES[4], '1.5m 이하입니다.', '섭씨 -5℃, 습도 80%입니다.',
                   '10~15m 거리입니다.', 'ABC 분말 소화기와 E-STOP을 확인하십시오.']
        manifest = []
        for i, text in enumerate(samples, 1):
            raw, fixed = target/f'{i:02d}_raw.wav', target/f'{i:02d}_fixed.wav'
            wav = engine.tts.synthesize(text, chunked=True)
            engine.sf.write(str(raw), wav, engine.sample_rate)
            if not engine.speak_to_file(text, str(fixed)):
                raise RuntimeError(f'합성 실패: {i}')
            manifest.append({'id': i, 'text': text, 'speech_text': local_pronunciation(text),
                             'raw': raw.name, 'fixed': fixed.name})
        (target/'clips.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(target/'audit.md')


if __name__ == '__main__':
    main()
