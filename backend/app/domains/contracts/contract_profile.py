"""ContractProfile + ContractCoverageAnalyzer — brief §22-23.

What clauses a contract "should" have depends on its type — an NDA has no
business having a delivery clause. Profiles are hand-authored per
ContractType (a legitimate judgment call, not something to infer from a
single contract), and coverage is computed by set difference against what
was actually extracted — fully deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.contracts.structure_extractor import ExtractedClause
from app.models.contracts import ClauseType, ContractType


@dataclass
class ContractProfile:
    required_clauses: set[ClauseType] = field(default_factory=set)
    recommended_clauses: set[ClauseType] = field(default_factory=set)
    optional_clauses: set[ClauseType] = field(default_factory=set)
    high_risk_clauses: set[ClauseType] = field(default_factory=set)


_BASE_REQUIRED = {ClauseType.SUBJECT, ClauseType.TERM, ClauseType.GOVERNING_LAW}

_PROFILES: dict[ContractType, ContractProfile] = {
    ContractType.SERVICE: ContractProfile(
        required_clauses=_BASE_REQUIRED | {ClauseType.PAYMENT, ClauseType.LIABILITY, ClauseType.TERMINATION},
        recommended_clauses={ClauseType.DISPUTE_RESOLUTION, ClauseType.CONFIDENTIALITY, ClauseType.FORCE_MAJEURE, ClauseType.ACCEPTANCE},
        optional_clauses={ClauseType.PENALTY, ClauseType.WARRANTY, ClauseType.INTELLECTUAL_PROPERTY},
        high_risk_clauses={ClauseType.LIABILITY, ClauseType.TERMINATION, ClauseType.PENALTY},
    ),
    ContractType.SUPPLY: ContractProfile(
        required_clauses=_BASE_REQUIRED | {ClauseType.PAYMENT, ClauseType.DELIVERY, ClauseType.LIABILITY},
        recommended_clauses={ClauseType.ACCEPTANCE, ClauseType.WARRANTY, ClauseType.DISPUTE_RESOLUTION, ClauseType.FORCE_MAJEURE},
        optional_clauses={ClauseType.PENALTY, ClauseType.INSURANCE},
        high_risk_clauses={ClauseType.LIABILITY, ClauseType.DELIVERY, ClauseType.PENALTY},
    ),
    ContractType.LEASE: ContractProfile(
        required_clauses=_BASE_REQUIRED | {ClauseType.PAYMENT, ClauseType.TERMINATION},
        recommended_clauses={ClauseType.RENEWAL, ClauseType.LIABILITY, ClauseType.NOTICE, ClauseType.INSURANCE},
        optional_clauses={ClauseType.ASSIGNMENT, ClauseType.AUDIT},
        high_risk_clauses={ClauseType.TERMINATION, ClauseType.RENEWAL},
    ),
    ContractType.NDA: ContractProfile(
        required_clauses={ClauseType.CONFIDENTIALITY, ClauseType.TERM, ClauseType.GOVERNING_LAW},
        recommended_clauses={ClauseType.NON_COMPETE, ClauseType.DISPUTE_RESOLUTION, ClauseType.TERMINATION},
        optional_clauses={ClauseType.PENALTY, ClauseType.INTELLECTUAL_PROPERTY},
        high_risk_clauses={ClauseType.CONFIDENTIALITY},
    ),
    ContractType.LICENSE: ContractProfile(
        required_clauses=_BASE_REQUIRED | {ClauseType.LICENSE, ClauseType.INTELLECTUAL_PROPERTY, ClauseType.PAYMENT},
        recommended_clauses={ClauseType.TERMINATION, ClauseType.LIABILITY, ClauseType.CONFIDENTIALITY, ClauseType.AUDIT},
        optional_clauses={ClauseType.NON_COMPETE, ClauseType.ASSIGNMENT},
        high_risk_clauses={ClauseType.INTELLECTUAL_PROPERTY, ClauseType.LICENSE, ClauseType.TERMINATION},
    ),
}

_DEFAULT_PROFILE = ContractProfile(
    required_clauses=_BASE_REQUIRED,
    recommended_clauses={ClauseType.LIABILITY, ClauseType.TERMINATION, ClauseType.DISPUTE_RESOLUTION},
)


def get_profile(contract_type: ContractType) -> ContractProfile:
    return _PROFILES.get(contract_type, _DEFAULT_PROFILE)


@dataclass
class CoverageResult:
    missing_required: set[ClauseType]
    missing_recommended: set[ClauseType]
    present: set[ClauseType]


def analyze_coverage(clauses: list[ExtractedClause], contract_type: ContractType) -> CoverageResult:
    profile = get_profile(contract_type)
    present = {c.clause_type for c in clauses}
    return CoverageResult(
        missing_required=profile.required_clauses - present,
        missing_recommended=profile.recommended_clauses - present,
        present=present,
    )
