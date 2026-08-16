"""Text normalization — Phase 9.2 brief §12. Deliberately conservative:
allowed to collapse whitespace/line-noise, never allowed to merge separate
lines together (that's exactly what would turn "4.1\n4.2\n4.3" into one
unstructured paragraph, which the brief explicitly forbids).
"""
from __future__ import annotations

import re
import unicodedata

_INTRA_LINE_WHITESPACE = re.compile(r"[ \t]+")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)

    lines = [_INTRA_LINE_WHITESPACE.sub(" ", line).rstrip() for line in text.split("\n")]

    normalized_lines: list[str] = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run <= 1:  # collapse 2+ consecutive blank lines to exactly one
                normalized_lines.append(line)
        else:
            blank_run = 0
            normalized_lines.append(line)

    return "\n".join(normalized_lines).strip()
