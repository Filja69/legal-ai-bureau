"""Confidence scoring (LEGAL-RAG.md §5) — computed from verification outcomes,
never asserted directly by the LLM.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfidenceInput:
    has_verified_norm_citation: bool
    has_verified_case_law: bool
    has_contradicting_position: bool
    has_unverified_load_bearing_citation: bool


def compute_confidence(inp: ConfidenceInput) -> str:
    if inp.has_unverified_load_bearing_citation:
        return "low"
    if inp.has_contradicting_position:
        return "low"
    if inp.has_verified_norm_citation and inp.has_verified_case_law:
        return "high"
    if inp.has_verified_norm_citation:
        return "medium"
    return "low"
