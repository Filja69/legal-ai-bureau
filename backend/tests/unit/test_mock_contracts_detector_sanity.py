"""Sanity check: each mock contract's deliberately-planted risks are actually
findable by the detectors before they're used in the eval suite (brief §69-70).
"""
from __future__ import annotations

import pytest

from app.domains.contracts.mock_contracts import MOCK_CONTRACTS
from app.domains.contracts.risk_detection import run_all_detectors
from app.domains.contracts.structure_extractor import ContractStructureExtractor
from app.models.contracts import ContractType


@pytest.mark.parametrize("record", MOCK_CONTRACTS, ids=lambda r: r["key"])
def test_mock_contract_planted_risks_are_detected(record):
    clauses = ContractStructureExtractor().extract(record["text"])
    candidates = run_all_detectors(clauses, ContractType(record["contract_type"]))
    found_types = {c.risk_type.value for c in candidates}

    missing = set(record["expected"]["critical_or_high_risks"]) - found_types
    assert not missing, f"{record['key']}: detectors missed expected risk types {missing}; found {found_types}"


def test_all_mock_contracts_have_at_least_five_clauses():
    for record in MOCK_CONTRACTS:
        clauses = ContractStructureExtractor().extract(record["text"])
        assert len(clauses) >= 5, f"{record['key']} has too few clauses ({len(clauses)})"


def test_mock_contracts_cover_all_five_types():
    types = {r["contract_type"] for r in MOCK_CONTRACTS}
    assert types == {"service", "supply", "nda", "license", "lease"}
