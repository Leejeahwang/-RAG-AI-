"""Deterministic speech-only notation fixes; never modify retrieval/source text.

Common fixes preserve quantities before markdown cleanup. Local fixes spell out
reviewed terms for Korean local engines without changing Gemini pronunciation.
Unknown formulas, identifiers and unsupported compound units are left alone.
"""
import re


_NUMBER = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
_UNITS = {
    'km/h': ('시속 ', '킬로미터'), 'm/s': ('초속 ', '미터'),
    '℃': ('섭씨 ', '도'), '°C': ('섭씨 ', '도'), '°F': ('화씨 ', '도'),
    '㎏': ('', '킬로그램'), 'kg': ('', '킬로그램'),
    '㎎': ('', '밀리그램'), 'mg': ('', '밀리그램'),
    '㎞': ('', '킬로미터'), 'km': ('', '킬로미터'),
    '㎝': ('', '센티미터'), 'cm': ('', '센티미터'),
    '㎜': ('', '밀리미터'), 'mm': ('', '밀리미터'),
    'm²': ('', '제곱미터'), '㎡': ('', '제곱미터'),
    'm³': ('', '세제곱미터'), '㎥': ('', '세제곱미터'), 'm': ('', '미터'),
    'mL': ('', '밀리리터'), 'ml': ('', '밀리리터'),
    'L': ('', '리터'), 'ℓ': ('', '리터'), '%': ('', '퍼센트'),
}
_UNIT_PATTERN = '|'.join(re.escape(key) for key in sorted(_UNITS, key=len, reverse=True))
_UNIT_END = r'(?![A-Za-z0-9²³/])'
_MEASURE = re.compile(r'(?<![A-Za-z0-9_.-])(?P<n>[-−]?' + _NUMBER +
                      r')\s*(?P<u>' + _UNIT_PATTERN + ')' + _UNIT_END)
_RANGE = re.compile(r'(?<![A-Za-z0-9_.])(?P<a>[-−]?' + _NUMBER +
                    r')\s*(?:~|～|〜|–|—|-)\s*(?P<b>[-−]?' + _NUMBER +
                    r')\s*(?P<u>' + _UNIT_PATTERN + ')' + _UNIT_END)


def _measure(number, unit):
    prefix, name = _UNITS[unit]
    if number.startswith(('-', '−')):
        number = '마이너스 ' + number[1:]
    return prefix + number + ' ' + name


def preserve_spoken_notation(text, lang='ko'):
    """Expand only explicit numeric units/ranges before destructive cleanup."""
    if lang != 'ko':
        return text
    text = _RANGE.sub(lambda m: _measure(m['a'], m['u']) + '에서 ' + _measure(m['b'], m['u']), text)
    text = _MEASURE.sub(lambda m: _measure(m['n'], m['u']), text)
    text = re.sub(r'(섭씨|화씨)\s*\1\s*', r'\1 ', text)
    text = re.sub(r'(?<![A-Za-z0-9_.])(' + _NUMBER + r')\s*(?:~|～|〜|–|—|-)\s*(' + _NUMBER +
                  r')\s*(초|분|시간|층|명|개|회|도)(?![A-Za-z0-9])', r'\1\3에서 \2\3', text)
    # Preserve negative Korean quantities too, but not hyphens in identifiers.
    text = re.sub(r'(?<![\w.])[-−](?=\d+(?:\.\d+)?\s*(?:도|미터|초|분|킬로그램))', '마이너스 ', text)
    text = re.sub(r'([ABC])\s*[·ㆍ]\s*(?=[ABC](?:\s*[·ㆍ]\s*[ABC])*\s*구역)', r'\1구역과 ', text)
    return text


_TERMS = {
    'CO2': '이산화탄소', 'CO₂': '이산화탄소',
    'N2': '질소', 'N₂': '질소', 'O2': '산소', 'O₂': '산소',
    'H2O': '물', 'H₂O': '물',
    'ABC': '에이비씨', 'BC': '비씨', 'CPR': '씨피알', 'GPS': '지피에스',
    'AED': '에이이디', 'AI': '에이아이', 'E-STOP': '이 스톱',
    'E/V': '엘리베이터',
}
_TERM_PATTERN = re.compile(r'(?<![A-Za-z0-9_])(?:' +
    '|'.join(re.escape(key) for key in sorted(_TERMS, key=len, reverse=True)) +
    r')(?![A-Za-z0-9_₂₃₄₅₆₇₈₉])', re.IGNORECASE)
_TERM_LOOKUP = {key.upper(): value for key, value in _TERMS.items()}
_DIGITS = '영일이삼사오육칠팔구'


def _integer(number):
    number = int(number)
    if number == 0:
        return '영'
    if number >= 10**16:
        raise ValueError('outside reviewed speech number range')
    parts = []
    for group_unit in ('', '만', '억', '조'):
        group, number = number % 10000, number // 10000
        syllables = []
        for place, unit in ((1000, '천'), (100, '백'), (10, '십'), (1, '')):
            digit, group = divmod(group, place)
            if digit:
                syllables.append(('' if digit == 1 and place > 1 else _DIGITS[digit]) + unit)
        if syllables:
            parts.append(''.join(syllables) + group_unit)
    return ''.join(reversed(parts))


def _spoken_number(match):
    value = match.group().replace(',', '')
    try:
        integer, dot, decimal = value.partition('.')
        return _integer(integer) + (' 점 ' + ''.join(_DIGITS[int(digit)] for digit in decimal) if dot else '')
    except ValueError:
        return match.group()


def local_pronunciation(text, lang='ko'):
    """Used by PPASO at its synthesis boundary, including direct wrapper calls."""
    if lang != 'ko':
        return text
    text = preserve_spoken_notation(text, lang)
    text = _TERM_PATTERN.sub(lambda m: _TERM_LOOKUP[m.group().upper()], text)
    # Identifiers and versions/IP addresses must not be read as decimal amounts.
    text = re.sub(r'(?<![A-Za-z0-9_.])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+)(?![A-Za-z0-9_]|\.\d)', _spoken_number, text)
    return text
