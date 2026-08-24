"""Master Case Report — the top-level synthesis layer over already-computed
E1-E4 + Case Intelligence data (allegations, payment orders/money flow,
claim-vs-evidence contradictions, claim-theory tensions, contract forensics,
payment-pattern conduct analysis, party relationships, missing evidence).

Zero LLM calls. Every finding is built by a bounded template rule keyed off
real, structured data — never off case-specific text matching. This module
is deliberately generic: nothing here references "BS Energo", "Ledovyi
Service", specific rubles, or specific dates. The golden-standard defense
memo this module was designed against is a benchmark for INFORMATION VALUE,
never a source of hardcoded logic — see the module-level test suite
(test_master_report.py), which exercises this entirely on synthetic data
different from the real case.

Design choices worth stating explicitly:
- `helps_side`/`hurts_side` on a finding are only ever "client"/"opponent"
  when the finding's direction is genuinely derivable from structured data
  (which party's allegation is undermined) AND `our_side_role` (which
  procedural role the case's own client holds) is known — otherwise
  "unclear"/"neutral", never guessed.
- CONTRACT_MISMATCH and PAYMENT_PATTERN findings are always "neutral" —
  the golden standard explicitly requires explaining both interpretations,
  never resolving a two-sided fact in one party's favor.
- Every section a lawyer might expect (court scenarios, opposing-party
  questions, draft response structure) is a template selection keyed off
  which finding categories are actually present in the case — not a
  hallucinated narrative.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.domains.litigation.case_relationships import PartyRelationshipFinding
from app.domains.litigation.case_result_summary import MissingEvidenceItem
from app.domains.litigation.conduct_patterns import PaymentPatternResult
from app.domains.litigation.contract_forensics import ContractVersionTerms
from app.domains.litigation.contradiction_detector import ClaimEvidenceContradiction, ClaimTheoryTension
from app.models.matters import AllegationType

if TYPE_CHECKING:
    from app.domains.litigation.pipeline import MoneyFlowSummary


class FindingCategory(str, enum.Enum):
    CLAIM_CONTRADICTION = "claim_contradiction"
    PAYMENT_PATTERN = "payment_pattern"
    CONTRACT_FORMATION = "contract_formation"
    CONTRACT_MISMATCH = "contract_mismatch"
    PARTY_CONDUCT = "party_conduct"
    INTEREST_CALCULATION = "interest_calculation"
    PROCEDURAL = "procedural"
    CORPORATE_RELATIONSHIP = "corporate_relationship"
    RELATED_LITIGATION = "related_litigation"
    EVIDENCE_GAP = "evidence_gap"
    LEGAL_ARGUMENT = "legal_argument"
    RISK = "risk"
    OTHER = "other"


@dataclass
class MasterFinding:
    id: str
    category: FindingCategory
    title: str
    statement: str
    supporting_facts: list[str] = field(default_factory=list)
    contradicting_facts: list[str] = field(default_factory=list)
    source_document_ids: list[uuid.UUID] = field(default_factory=list)
    source_document_titles: list[str] = field(default_factory=list)
    excerpts: list[str] = field(default_factory=list)
    page_numbers: list[int | None] = field(default_factory=list)
    helps_side: str = "unclear"  # "client" | "opponent" | "neutral" | "unclear"
    hurts_side: str = "unclear"
    strength: str = "MEDIUM"  # CRITICAL | HIGH | MEDIUM | LOW
    confidence: str = ""
    legal_significance: str = ""
    counterargument: str | None = None
    response_to_counterargument: str | None = None
    caveat: str | None = None
    missing_evidence: list[str] = field(default_factory=list)
    recommended_action: str | None = None
    verification_status: str = "document_supported"


def _allegation_author_side(our_side_role: str) -> tuple[str, str]:
    """Case allegations are extracted from CLAIM/RESPONSE/COURT_FILING
    documents — the pleading party. If our client holds the "plaintiff"
    role, the client authored the allegations (so an allegation-undermining
    finding hurts the client); if our client is "defendant", the opponent
    authored them. Returns (helps_side, hurts_side) for a finding that
    UNDERMINES an allegation. "unclear" role -> both "unclear", never guessed.
    """
    if our_side_role == "plaintiff":
        return "opponent", "client"
    if our_side_role == "defendant":
        return "client", "opponent"
    return "unclear", "unclear"


def build_claim_contradiction_findings(
    claim_evidence: list[ClaimEvidenceContradiction],
    theory_tensions: list[ClaimTheoryTension],
    document_titles: dict[uuid.UUID, str],
    our_side_role: str,
) -> list[MasterFinding]:
    helps, hurts = _allegation_author_side(our_side_role)
    findings: list[MasterFinding] = []

    for i, c in enumerate(claim_evidence):
        findings.append(
            MasterFinding(
                id=f"claim_contradiction:evidence:{i}",
                category=FindingCategory.CLAIM_CONTRADICTION,
                title="Pleading contradicted by the party's own executed document",
                statement=c.reason,
                source_document_ids=[c.allegation_document_id, c.evidence_document_id],
                source_document_titles=[
                    document_titles.get(c.allegation_document_id, "(deleted)"),
                    document_titles.get(c.evidence_document_id, "(deleted)"),
                ],
                excerpts=[c.allegation_excerpt, c.evidence_excerpt],
                page_numbers=[c.allegation_page, c.evidence_page],
                helps_side=helps, hurts_side=hurts, strength="HIGH", confidence=c.confidence,
                legal_significance="Relevant to the factual/legal basis of the transfer; not dispositive alone.",
                caveat=c.caveat,
                recommended_action="Obtain correspondence around the referenced date to establish the parties' actual understanding.",
                verification_status="document_supported",
            )
        )

    for i, t in enumerate(theory_tensions):
        findings.append(
            MasterFinding(
                id=f"claim_contradiction:theory:{i}",
                category=FindingCategory.CLAIM_CONTRADICTION,
                title="Internal tension between two propositions in the same pleading",
                statement=t.reason,
                source_document_ids=[t.allegation_a_document_id, t.allegation_b_document_id],
                source_document_titles=[
                    document_titles.get(t.allegation_a_document_id, "(deleted)"),
                    document_titles.get(t.allegation_b_document_id, "(deleted)"),
                ],
                excerpts=[t.allegation_a_excerpt, t.allegation_b_excerpt],
                helps_side=helps, hurts_side=hurts, strength="HIGH",
                confidence="Deterministic — both propositions come from the same party's own pleading.",
                legal_significance="A pleading asserting two different factual postures for the same transfer invites scrutiny of both.",
                caveat=(
                    "This identifies a tension worth investigating, not a resolved inconsistency — the two "
                    "propositions could in principle be reconciled with additional context."
                ),
                recommended_action=(
                    "Confirm with the client whether both propositions are actually maintained, or clarify "
                    "which one is the operative theory."
                ),
                verification_status="document_supported",
            )
        )
    return findings


def build_payment_pattern_finding(pattern: PaymentPatternResult) -> MasterFinding | None:
    if not pattern.is_significant:
        return None
    return MasterFinding(
        id="payment_pattern:money_flow",
        category=FindingCategory.PAYMENT_PATTERN,
        title="Payments span an extended period across multiple transactions",
        statement=pattern.description,
        helps_side="neutral", hurts_side="neutral", strength="MEDIUM",
        confidence=f"{pattern.transaction_count} transactions, {pattern.span_days}-day span — deterministic count from Money Flow.",
        legal_significance="Relevant to characterizing the transfers as an isolated event versus a sustained course of conduct.",
        caveat="This pattern alone does not establish either party's characterization of the underlying transaction.",
        recommended_action="Cross-reference against correspondence/accounting records covering the same period.",
    )


def build_contract_mismatch_finding(matrix: list[ContractVersionTerms], money_flow_total: str) -> MasterFinding | None:
    all_amounts = {a for terms in matrix for a in terms.amounts}
    if len(matrix) < 2 and money_flow_total in all_amounts:
        return None
    if not all_amounts or (len(all_amounts) <= 1 and money_flow_total in all_amounts):
        return None

    return MasterFinding(
        id="contract_mismatch:versions",
        category=FindingCategory.CONTRACT_MISMATCH,
        title="Contract version(s) do not state a single amount matching the funds actually transferred",
        statement=(
            f"{len(matrix)} contract document(s) were found, stating amount(s) {sorted(all_amounts)}, while the "
            f"total amount actually transferred (per Money Flow) is {money_flow_total}."
        ),
        source_document_ids=[t.document_id for t in matrix],
        source_document_titles=[t.document_title for t in matrix],
        helps_side="neutral", hurts_side="neutral", strength="MEDIUM",
        confidence="Deterministic — extracted amounts compared directly against Money Flow total.",
        legal_significance=(
            "This may support either interpretation: an ongoing negotiation over the amount that never fully "
            "settled (consistent with a negotiation narrative), or a failure to agree on an essential term "
            "(consistent with a no-contract narrative)."
        ),
        caveat="Neither interpretation is established by the mismatch alone — both must be argued from the full record.",
        recommended_action="Obtain correspondence discussing the loan amount to determine which figure (if any) was actually agreed.",
        verification_status="document_supported",
    )


def build_contract_formation_findings(matrix: list[ContractVersionTerms]) -> list[MasterFinding]:
    findings: list[MasterFinding] = []
    for terms in matrix:
        if terms.signature_status == "confirmed_signed":
            continue
        description = {
            "unsigned_or_draft": "its own text indicates it is a draft or unsigned",
            "unknown": "signature status cannot be confirmed from its text",
        }.get(terms.signature_status, "signature status is undetermined")
        findings.append(
            MasterFinding(
                id=f"contract_formation:{terms.document_id}",
                category=FindingCategory.CONTRACT_FORMATION,
                title="Contract document without a confirmed signed copy",
                statement=f"Document '{terms.document_title}' {description}.",
                source_document_ids=[terms.document_id], source_document_titles=[terms.document_title],
                helps_side="unclear", hurts_side="unclear", strength="MEDIUM",
                confidence="Text-based signature-status classification, not a legal conclusion.",
                legal_significance=(
                    "A confirmed signed copy is significant evidence of formation; its absence leaves the "
                    "question open, not resolved either way."
                ),
                caveat=(
                    "Absence of a confirmed signature does not establish the contract was never concluded — "
                    "formation may still be argued from conduct."
                ),
                missing_evidence=["Signed copy of this contract document, if one exists"],
                recommended_action="Search for a countersigned copy of this document before relying on its absence.",
            )
        )
    return findings


def build_evidence_gap_findings(missing: list[MissingEvidenceItem]) -> list[MasterFinding]:
    return [
        MasterFinding(
            id=f"evidence_gap:{i}",
            category=FindingCategory.EVIDENCE_GAP,
            title="Missing critical evidence",
            statement=item.description,
            helps_side="unclear", hurts_side="unclear", strength="HIGH" if item.priority == "CRITICAL" else "MEDIUM",
            confidence="Derived from document-role presence in the case, not a claim about the outside world.",
            legal_significance=item.why_it_matters,
            missing_evidence=[item.description],
            recommended_action=f"Obtain: {item.description}",
            source_document_ids=[item.source_document_id] if item.source_document_id else [],
            source_document_titles=[item.source_document_title] if item.source_document_title else [],
        )
        for i, item in enumerate(missing)
    ]


@dataclass
class RelatedLitigationInput:
    id: uuid.UUID
    case_number: str | None
    court: str | None
    subject_matter: str | None
    amount_in_dispute: str | None


def build_related_litigation_findings(related: list[RelatedLitigationInput]) -> list[MasterFinding]:
    """Wraps each CaseRelatedLitigation row into a LOW-strength, neutral
    finding — context only, never evidence of motive. Reuses
    `case_relationships.py`'s causal-safe note verbatim as the statement,
    so this can never drift from that discipline into a stronger claim.
    """
    from app.domains.litigation.case_relationships import build_related_litigation_note

    findings: list[MasterFinding] = []
    for i, r in enumerate(related):
        detail_parts = [p for p in (r.court, r.subject_matter, r.amount_in_dispute) if p]
        findings.append(
            MasterFinding(
                id=f"related_litigation:{i}",
                category=FindingCategory.RELATED_LITIGATION,
                title=f"Related proceeding{f' ({r.case_number})' if r.case_number else ''}",
                statement=build_related_litigation_note(r.case_number),
                supporting_facts=detail_parts,
                helps_side="neutral", hurts_side="neutral", strength="LOW",
                confidence="Reported by counsel — not independently verified by this system.",
                legal_significance="May warrant investigation as contextual information only.",
                caveat="Does not establish that this proceeding caused or motivated the present case.",
                missing_evidence=["Independent confirmation of this proceeding's existence, status, and timing"],
                verification_status="unverified",
            )
        )
    return findings


def build_corporate_relationship_findings(relationship_findings: list[PartyRelationshipFinding]) -> list[MasterFinding]:
    return [
        MasterFinding(
            id=f"corporate_relationship:{i}",
            category=FindingCategory.CORPORATE_RELATIONSHIP,
            title=f"{f.subject_name} — {f.relationship_type.value} of {f.related_party_name}",
            statement=f.why_it_may_matter,
            helps_side="unclear", hurts_side="unclear", strength="MEDIUM",
            confidence=f"Verification status: {f.verification_status.value}.",
            legal_significance=f.timing_note,
            caveat="Corporate status alone does not establish actual knowledge of the transaction.",
            missing_evidence=f.what_is_still_needed,
            source_document_ids=[f.source_document_id] if f.source_document_id else [],
            source_document_titles=[f.source_document_title] if f.source_document_title else [],
            excerpts=[f.source_excerpt] if f.source_excerpt else [],
            verification_status=f.verification_status.value,
        )
        for i, f in enumerate(relationship_findings)
    ]


def rank_findings(findings: list[MasterFinding]) -> list[MasterFinding]:
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    return sorted(findings, key=lambda f: order.get(f.strength, 4))


# --- One-Pager, Court Scenarios, Questions, Draft Response Structure ---


@dataclass
class CaseOnePager:
    case_position: str
    strongest_point: str | None
    biggest_risk: str | None
    money_at_stake: str
    top_arguments: list[str]
    top_risks: list[str]
    what_opponent_must_explain: list[str]
    what_court_likely_focuses_on: str | None
    missing_p0_evidence: list[str]
    next_best_action: str | None


def build_one_pager(
    findings: list[MasterFinding], money_at_stake: str, next_best_action: str | None
) -> CaseOnePager:
    ranked = rank_findings(findings)
    helps_client = [f for f in ranked if f.helps_side == "client"]
    hurts_client = [f for f in ranked if f.hurts_side == "client"] + [
        f for f in ranked if f.category == FindingCategory.EVIDENCE_GAP and f.strength in ("CRITICAL", "HIGH")
    ]
    opponent_undermined = [f for f in ranked if f.hurts_side == "opponent" and f.category == FindingCategory.CLAIM_CONTRADICTION]

    return CaseOnePager(
        case_position=(
            f"{len(findings)} finding(s) identified across the case record — see sections below for the full analysis."
        ),
        strongest_point=helps_client[0].title if helps_client else (ranked[0].title if ranked else None),
        biggest_risk=hurts_client[0].title if hurts_client else None,
        money_at_stake=money_at_stake,
        top_arguments=[f.title for f in helps_client[:3]] or [f.title for f in ranked[:3]],
        top_risks=[f.title for f in hurts_client[:3]],
        what_opponent_must_explain=[f.statement for f in opponent_undermined[:3]],
        what_court_likely_focuses_on=ranked[0].legal_significance if ranked else None,
        missing_p0_evidence=[m for f in findings for m in f.missing_evidence][:5],
        next_best_action=next_best_action,
    )


@dataclass
class CourtScenario:
    scenario: str
    why_court_could_get_there: str
    facts_supporting: list[str]
    facts_against: list[str]
    label: str = "STRATEGIC SCENARIO — NOT A COURT PREDICTION"


def build_court_scenarios(findings: list[MasterFinding]) -> list[CourtScenario]:
    """A small, fixed template bank keyed by which finding CATEGORIES are
    present — never by case-specific text. Deliberately generic scenario
    language; never a probability percentage.
    """
    categories_present = {f.category for f in findings}
    scenarios: list[CourtScenario] = []

    if FindingCategory.CLAIM_CONTRADICTION in categories_present:
        scenarios.append(
            CourtScenario(
                scenario=(
                    "Court finds the pleading's internal tensions significant enough to require closer "
                    "factual scrutiny of the claimed theory."
                ),
                why_court_could_get_there="Two propositions in the same pleading describe different factual postures for the same events.",
                facts_supporting=[f.title for f in findings if f.category == FindingCategory.CLAIM_CONTRADICTION],
                facts_against=["A pleading may lawfully argue in the alternative; tension alone does not resolve the merits."],
            )
        )
    if FindingCategory.CONTRACT_MISMATCH in categories_present or FindingCategory.CONTRACT_FORMATION in categories_present:
        scenarios.append(
            CourtScenario(
                scenario=(
                    "Court finds an underlying contractual or quasi-contractual basis existed, despite the "
                    "absence of a single fully-executed document."
                ),
                why_court_could_get_there=(
                    "Multiple contract documents and/or conduct consistent with an ongoing negotiation exist in the record."
                ),
                facts_supporting=[
                    f.title for f in findings
                    if f.category in (FindingCategory.CONTRACT_MISMATCH, FindingCategory.CONTRACT_FORMATION)
                ],
                facts_against=["No single document is fully executed by both parties on consistent terms."],
            )
        )
    if FindingCategory.PAYMENT_PATTERN in categories_present:
        scenarios.append(
            CourtScenario(
                scenario=(
                    "Court treats the transfers as a sustained course of conduct rather than an isolated "
                    "event, affecting how it weighs the parties' intent."
                ),
                why_court_could_get_there="The payment pattern spans a significant period and multiple separate transactions.",
                facts_supporting=[f.title for f in findings if f.category == FindingCategory.PAYMENT_PATTERN],
                facts_against=["A pattern of transfers does not itself establish what the parties agreed, if anything."],
            )
        )
    scenarios.append(
        CourtScenario(
            scenario="Court substantially adopts the claimant's theory as pleaded.",
            why_court_could_get_there=(
                "Realized whenever the record does not sufficiently develop the counter-narrative — always "
                "a live baseline scenario."
            ),
            facts_supporting=["Absence of the missing evidence identified in this report would make this more likely."],
            facts_against=[f.title for f in findings if f.strength in ("CRITICAL", "HIGH")],
        )
    )
    return scenarios


_QUESTION_TEMPLATES: dict[FindingCategory, list[str]] = {
    FindingCategory.PAYMENT_PATTERN: [
        "Why were the transfers made as multiple separate transactions rather than a single payment?",
        "Who authorized each individual transfer, and on what basis?",
        "Why was no return of funds demanded immediately after the first transfer?",
    ],
    FindingCategory.CLAIM_CONTRADICTION: [
        "When did the party first take the position reflected in this pleading?",
        "How do you reconcile the two propositions identified in this finding?",
    ],
    FindingCategory.CONTRACT_MISMATCH: [
        "Which of the contract document(s) in the record, if any, reflects the parties' final agreement on amount?",
        "Who prepared each version of the contract document, and when was each sent to the other party?",
    ],
    FindingCategory.CONTRACT_FORMATION: [
        "Does your side hold a fully signed copy of this document?",
        "What happened to the counterpart signature after the document was circulated?",
    ],
    FindingCategory.CORPORATE_RELATIONSHIP: [
        "When precisely did this relationship begin, and what corporate records establish that date?",
        "What access, if any, did this person have to the other party's internal information during the relevant period?",
    ],
}


def build_opposing_party_questions(findings: list[MasterFinding]) -> list[str]:
    questions: list[str] = []
    for category in sorted({f.category for f in findings}, key=lambda c: c.value):
        questions.extend(_QUESTION_TEMPLATES.get(category, []))
    return questions


@dataclass
class DraftResponseSection:
    section: str
    argument: str
    supporting_finding_ids: list[str]
    caution: str | None = None


_RESPONSE_STRUCTURE_TEMPLATE: list[tuple[str, str]] = [
    ("Вводная позиция", "State the overall position on the claim."),
    ("Фактические обстоятельства", "Chronological factual narrative, sourced from the case record."),
    ("Основание перечислений / договорные отношения", "Address contract formation and money-flow findings."),
    ("Внутренние противоречия истца", "Address claim-contradiction findings."),
    ("Проценты / убытки", "Address interest-calculation findings, if any."),
    ("Процессуальные вопросы", "Address procedural findings, if any."),
    ("Доказательства", "List and describe attached evidence."),
]


@dataclass
class BurdenItem:
    proposition: str
    side: str  # "client" | "opponent" | "unclear"
    current_evidence: list[str]
    contrary_evidence: list[str]
    status: str  # "supported" | "contested" | "unsupported"
    weakness: str | None
    how_to_attack: str | None


def build_burden_map(
    allegation_types_present: set[AllegationType], claim_contradiction_findings: list[MasterFinding], our_side_role: str
) -> list[BurdenItem]:
    """One item per distinct allegation type actually found in the case —
    never a fixed list of propositions, since a different case will assert
    different things.
    """
    # The allegation's own author is whichever side is HURT when the allegation is undermined.
    _, author_side = _allegation_author_side(our_side_role)

    items: list[BurdenItem] = []
    for allegation_type in sorted(allegation_types_present, key=lambda a: a.value):
        contrary = [f.statement for f in claim_contradiction_findings]
        items.append(
            BurdenItem(
                proposition=f"Proposition: {allegation_type.value.replace('_', ' ')}",
                side=author_side,
                current_evidence=[f"Pleading assertion of type '{allegation_type.value}'"],
                contrary_evidence=contrary,
                status="contested" if contrary else "unsupported",
                weakness=(
                    "Contradicted by the party's own evidence — see claim_contradiction findings." if contrary else None
                ),
                how_to_attack=(
                    "Rely on the identified claim-contradiction findings and request supporting correspondence."
                    if contrary else None
                ),
            )
        )
    return items


@dataclass
class CaseMapEntry:
    claimed_amounts: list[str]
    claim_dates: list[str]
    note: str


def build_case_map(claim_document_amounts: list[str], claim_document_dates: list[str]) -> CaseMapEntry:
    return CaseMapEntry(
        claimed_amounts=claim_document_amounts,
        claim_dates=claim_document_dates,
        note=(
            "Filing date, procedural stage, and next hearing are not derivable from static case documents and "
            "are not reported here — see MISSING EVIDENCE."
            if not claim_document_dates
            else (
                "Dates shown are all dates found in CLAIM-role documents; procedural stage/next hearing "
                "are not derivable from static documents."
            )
        ),
    )


@dataclass
class MasterCaseReport:
    one_pager: CaseOnePager
    case_map: CaseMapEntry
    findings: list[MasterFinding]
    burden_map: list[BurdenItem]
    court_scenarios: list[CourtScenario]
    opposing_party_questions: list[str]
    draft_response_structure: list[DraftResponseSection]
    contract_version_matrix: list[ContractVersionTerms]
    money_flow: MoneyFlowSummary
    legal_kb_warning: str | None


def build_draft_response_structure(findings: list[MasterFinding]) -> list[DraftResponseSection]:
    by_category: dict[FindingCategory, list[MasterFinding]] = {}
    for f in findings:
        by_category.setdefault(f.category, []).append(f)

    category_by_section: dict[str, FindingCategory | None] = {
        "Основание перечислений / договорные отношения": FindingCategory.CONTRACT_FORMATION,
        "Внутренние противоречия истца": FindingCategory.CLAIM_CONTRADICTION,
        "Проценты / убытки": FindingCategory.INTEREST_CALCULATION,
        "Процессуальные вопросы": FindingCategory.PROCEDURAL,
    }

    sections: list[DraftResponseSection] = []
    for section, argument in _RESPONSE_STRUCTURE_TEMPLATE:
        relevant_category = category_by_section.get(section)
        relevant = by_category.get(relevant_category, []) if relevant_category else []
        sections.append(
            DraftResponseSection(
                section=section, argument=argument, supporting_finding_ids=[f.id for f in relevant],
                caution="No findings currently support this section — do not overstate." if relevant_category and not relevant else None,
            )
        )
    return sections
