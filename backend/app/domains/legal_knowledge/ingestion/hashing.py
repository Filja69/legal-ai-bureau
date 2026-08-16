"""Deterministic content hashing — LEGAL-SOURCES.md §17.

Used for duplicate detection, change detection, provenance, and ingestion
idempotency. Hashing the *normalized* content (not raw) means whitespace/
encoding differences between two fetches of the same underlying text don't
produce spurious "new" documents.
"""
from __future__ import annotations

import hashlib


def content_hash(normalized_content: str) -> str:
    return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
