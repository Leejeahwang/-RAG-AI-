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
