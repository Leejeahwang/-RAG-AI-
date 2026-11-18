"""Shared intent rules for retrieval and ranking."""
import re


def medical_intent(query: str) -> str | None:
    text = re.sub(r"\s+", "", query.lower())
    # A generic mention of breathing (e.g. smoke exposure) is not a CPR query.
    if any(word in text for word in ("cpr", "심폐", "소생", "심정지", "호흡이없", "호흡없",
                                    "숨을안쉬", "숨안쉬", "숨을안쉰", "숨안쉰", "호흡을안",
                                    "의식이없", "의식없", "의식을잃")):
        return "cpr"
    if any(word in text for word in ("지혈", "출혈", "피가멈추지", "피가안멈", "피가철철")):
        return "bleeding"
    if any(word in text for word in ("골절", "부목", "뼈가부러", "추락", "떨어져서")):
        return "injury"
    if any(word in text for word in ("압박", "의식", "호흡", "상처", "응급")):
        return "medical"
    return None


def matches_medical_content(content: str, intent: str) -> bool:
    keywords = {
        "cpr": ("심폐소생", "심정지", "cpr", "가슴 압박", "가슴압박"),
        "bleeding": ("지혈", "출혈"),
        "injury": ("골절", "부목", "경추"),
        "medical": ("응급", "심폐", "지혈", "골절"),
    }
    return any(word in content.lower() for word in keywords[intent])
