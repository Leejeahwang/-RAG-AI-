"""명시된 구역의 로컬 대피경로 파일을 답변 컨텍스트에 추가한다."""

from pathlib import Path
import re


_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_ROUTE_TERMS = ("대피", "피난", "경로", "출구", "계단", "소화기", "위치")


def zone_from_text(text: str) -> str | None:
    if (text or "").strip().upper() in {"A", "B", "C"}:
        return text.strip().upper()
    match = re.search(r"([ABC])\s*구역", text or "", re.IGNORECASE)
    if not match:
        match = re.search(r"zone[_\s-]*([ABC])\b", text or "", re.IGNORECASE)
    return match.group(1).upper() if match else None


def layout_for_zone(zone: str) -> str:
    zone_id = zone_from_text(zone)
    if not zone_id:
        return ""
    path = _DATA_DIR / f"zone_{zone_id}_layout.txt"
    if not path.is_file():
        return ""
    return f"[현재 현장 {zone_id}구역 평면도 및 대피로]\n{path.read_text(encoding='utf-8')}\n\n"


def layout_for_question(question: str) -> str:
    if not any(term in question for term in _ROUTE_TERMS):
        return ""
    return layout_for_zone(question)


def evacuation_for_zone(zone: str) -> str:
    """Copy explicit routes and zone precautions; never infer a missing route."""
    layout = layout_for_zone(zone)
    lines = []
    in_routes = False
    for raw in layout.splitlines():
        line = raw.strip()
        if re.match(r"[-*]\s*화재 시 대피로\s*:", line):
            in_routes = True
            inline = line.split(":", 1)[1].strip()
            if inline:
                lines.append(inline)
        elif re.match(r"[-*]\s*특이사항\s*:", line):
            in_routes = False
            lines.append(line.split(":", 1)[1].strip())
        elif in_routes and re.match(r"\d+[.)]\s", line):
            lines.append(line)
        elif line.startswith(("-", "*", "#", "[")):
            in_routes = False
    if not lines:
        return ""
    return f"{zone_from_text(zone)}구역 대피 안내.\n" + "\n".join(lines)
