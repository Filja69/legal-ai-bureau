"""Redline diff — brief §38-40. A real word-level diff (Python's
`difflib.SequenceMatcher`), not "here's the new text" — every change is
categorized as equal/insert/delete so a side-by-side view can render it.

brief §40 explicitly says: if genuine Word Track Changes isn't implemented,
don't simulate it — build a side-by-side diff and say so plainly. That's
exactly what this produces; DOCX export with real tracked-changes XML is
NOT implemented (see Phase 4 report).
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

_WORD_PATTERN = re.compile(r"\S+|\s+")


@dataclass
class DiffOp:
    op: str  # "equal" | "insert" | "delete"
    text: str


def word_diff(original: str, proposed: str) -> list[DiffOp]:
    original_tokens = _WORD_PATTERN.findall(original)
    proposed_tokens = _WORD_PATTERN.findall(proposed)

    matcher = difflib.SequenceMatcher(a=original_tokens, b=proposed_tokens, autojunk=False)
    ops: list[DiffOp] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            ops.append(DiffOp(op="equal", text="".join(original_tokens[i1:i2])))
        elif tag == "delete":
            ops.append(DiffOp(op="delete", text="".join(original_tokens[i1:i2])))
        elif tag == "insert":
            ops.append(DiffOp(op="insert", text="".join(proposed_tokens[j1:j2])))
        elif tag == "replace":
            ops.append(DiffOp(op="delete", text="".join(original_tokens[i1:i2])))
            ops.append(DiffOp(op="insert", text="".join(proposed_tokens[j1:j2])))
    return ops


def diff_ops_to_dicts(ops: list[DiffOp]) -> list[dict]:
    return [{"op": o.op, "text": o.text} for o in ops]
