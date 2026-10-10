"""Prepare retrieved passages without dropping evidence from the same file."""

import re


def build_manual_context(documents):
    chunks = []
    seen_contents = set()
    for document in documents:
        lines = []
        for raw_line in document.get("page_content", "").splitlines():
            line = raw_line.strip()
            if re.match(r"^(?:#{1,6}\s*)?\[(?:위치|출처):", line):
                continue
            if re.fullmatch(r"[-*_]{3,}", line):
                continue
            # Headings identify conditions (e.g. electric fire); keep their text.
            lines.append(re.sub(r"^#{1,6}\s+", "", line))
        content = "\n".join(lines).strip()
        key = re.sub(r"\s+", " ", content)
        if key and key not in seen_contents:
            seen_contents.add(key)
            chunks.append(content)
    return "\n\n".join(chunks)


def additional_fire_context(documents):
    """Zone layouts are already broadcast locally; retain the response manuals."""
    candidates = [
        doc for doc in documents
        if not re.search(r"zone_[A-Z]_layout\.txt", str(doc.get("source", "")), re.I)
        and not re.match(r"\s*(?:#{1,6}\s*)?[ABC]구역\s*\(", doc.get("page_content", ""))
    ]
    # This application monitors factory zones. Broad vector retrieval can also
    # return first-aid/gas-poisoning advice; do not mix it into a fire broadcast.
    factory = [doc for doc in candidates
               if re.search(r"factory|공장", str(doc.get("source", "")), re.I)]
    fire = [doc for doc in candidates
            if re.search(r"fire|화재|소방", str(doc.get("source", "")), re.I)]
    return build_manual_context(factory or fire)


def without_repeated_guidance(answer, announced):
    def key(line):
        line = re.sub(r"^\s*(?:[-*•]\s+|\d+[.)]\s+|#{1,6}\s+)", "", line)
        return re.sub(r"[\s*`\"'‘’“”]", "", line)
    existing = {key(line) for line in announced.splitlines() if key(line)}
    kept = []
    for line in answer.splitlines():
        normalized = key(line)
        if normalized and normalized not in existing:
            kept.append(line)
            existing.add(normalized)
    return "\n".join(kept)


def instruction_passages(context):
    """Offer actions, not document titles; keep a condition with its action."""
    passages = []
    condition = ""
    for raw in context.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^(?:\[|#{1,6}\s|[-*]\s*(?:위치|소화기 위치):)", line):
            condition = ""
            continue
        plain = re.sub(r"[*`\"'‘’“”]", "", line).strip()
        action = bool(re.search(r"(?:[.!?。]|하십시오|합니다|하세요|할 것|해야 해|됩니다|마세요)$", plain))
        if not action:
            condition = line if line.startswith(("*", "•")) else ""
            continue
        # A stand-alone bullet is its own instruction; nested '-' actions belong
        # to the preceding condition (e.g. electrical vs chemical fire).
        if line.startswith(("*", "•")):
            condition = ""
        passage = condition+"\n"+line if condition else line
        if passage not in passages:
            passages.append(passage)
    return passages
