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
from datetime import date
from typing import TYPE_CHECKING

from app.domains.litigation.case_relationships import PartyRelationshipFinding, classify_relationship_timing
from app.domains.litigation.case_result_summary import MissingEvidenceItem
from app.domains.litigation.conduct_patterns import PaymentPatternResult
from app.domains.litigation.contract_forensics import ContractVersionTerms
from app.domains.litigation.contradiction_detector import ClaimEvidenceContradiction, ClaimTheoryTension
from app.domains.litigation.course_of_dealing import CourseOfDealingResult
from app.domains.litigation.interest_damages import InterestCalculationSummary, InterestClaimResult
from app.domains.litigation.notice_timeline import NoticeTimelineResult
from app.domains.litigation.temporal_reasoning import TemporalIssue
from app.models.matters import AllegationType

if TYPE_CHECKING:
    from app.domains.litigation.pipeline import MoneyFlowSummary


class FindingCategory(str, enum.Enum):
    CLAIM_CONTRADICTION = "claim_contradiction"
    PAYMENT_PATTERN = "payment_pattern"
    CONTRACT_FORMATION = "contract_formation"
    CONTRACT_MISMATCH = "contract_mismatch"
    COURSE_OF_DEALING = "course_of_dealing"
    PARTY_CONDUCT = "party_conduct"
    INTEREST_CALCULATION = "interest_calculation"
    PROCEDURAL = "procedural"
    CORPORATE_RELATIONSHIP = "corporate_relationship"
    RELATED_LITIGATION = "related_litigation"
    EVIDENCE_GAP = "evidence_gap"
    LEGAL_ARGUMENT = "legal_argument"
    RISK = "risk"
    TIMING = "timing"
    SYNTHESIS = "synthesis"
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
    # Adversarial/self-critical fields (case_reasoning_graph brief §6) — left
    # empty unless the builder that produces this finding actually has
    # something non-fabricated to say; never populated generically.
    alternative_explanations: list[str] = field(default_factory=list)
    what_would_strengthen: list[str] = field(default_factory=list)
    what_would_weaken: list[str] = field(default_factory=list)
    legal_research_required: bool = False
    # Finding ids (MasterFinding.id) this finding cross-links into one
    # synthesized observation — empty for an ordinary standalone finding;
    # populated only for a FindingCategory.SYNTHESIS finding (Part 5).
    synthesizes: list[str] = field(default_factory=list)


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


def build_course_of_dealing_finding(result: CourseOfDealingResult) -> MasterFinding | None:
    if not result.is_significant:
        return None
    return MasterFinding(
        id="course_of_dealing:money_flow",
        category=FindingCategory.COURSE_OF_DEALING,
        title="Payments reference more than one contractual date",
        statement=result.description,
        helps_side="neutral", hurts_side="neutral",
        strength="HIGH" if result.matching_term_document_pairs > 0 else "MEDIUM",
        confidence=(
            f"{len(result.distinct_contract_dates)} distinct referenced contract dates — deterministic count "
            "from Money Flow."
        ),
        legal_significance=(
            "May be relevant to whether the parties had an ongoing or renewed lending relationship, rather "
            "than a single isolated transaction — a question the parties' full course of dealing bears on."
        ),
        caveat=(
            "A later contractual reference does not by itself prove an earlier arrangement's terms or "
            "existence, and an earlier reference does not by itself extend to cover a later, separately-"
            "referenced transfer — this must be argued from the full record, not assumed from the dates alone."
        ),
        alternative_explanations=[
            "The parties entered a genuinely new, separate agreement unrelated to the earlier reference.",
            "The later reference formalizes or renews the same underlying lending relationship as the earlier one.",
        ],
        what_would_strengthen=[
            "Correspondence or accounting records showing how the parties themselves treated the two references.",
        ],
        recommended_action=(
            "Obtain the full text of each referenced contract and any correspondence discussing how the "
            "transfers relate to each other."
        ),
    )


_MISTAKE_LIKE_ALLEGATIONS = frozenset({AllegationType.PAYMENT_BY_MISTAKE, AllegationType.NO_LEGAL_BASIS})


def build_theory_vs_conduct_finding(
    allegation_types_present: set[AllegationType], pattern: PaymentPatternResult
) -> MasterFinding | None:
    """Cross-links two independently-computed signals — allegation type
    (E1) and payment-pattern significance (conduct_patterns.py) — into one
    finding. Never declares the allegation false; the tension is framed as
    something inviting scrutiny, exactly like every other tension this
    package detects.
    """
    matched_types = allegation_types_present & _MISTAKE_LIKE_ALLEGATIONS
    if not pattern.is_significant or not matched_types:
        return None
    type_labels = ", ".join(sorted(t.value for t in matched_types))
    return MasterFinding(
        id="theory_vs_conduct:payment_pattern",
        category=FindingCategory.PARTY_CONDUCT,
        title="Repeated payment conduct may be in tension with a mistake/no-legal-basis theory",
        statement=(
            f"The pleading asserts '{type_labels}', while the payment pattern in this case ({pattern.description}) "
            "reflects repeated, similarly-purposed transfers. A pattern of repeated conduct may invite scrutiny "
            "of a mistake-based theory, though it does not by itself disprove it."
        ),
        helps_side="neutral", hurts_side="neutral", strength="MEDIUM",
        confidence="Deterministic — allegation type(s) and payment-pattern significance both computed from structured case data.",
        legal_significance=(
            "A repeated pattern of similarly-purposed transfers is conduct a court may weigh against a claim "
            "that each transfer was independently mistaken or without legal basis."
        ),
        caveat=(
            "Repeated conduct alone does not establish that any individual transfer was not mistaken — each "
            "instance must still be assessed on its own facts."
        ),
        alternative_explanations=["Each transfer could have been independently and separately mistaken, notwithstanding the pattern."],
        recommended_action="Obtain correspondence or internal records showing whether each transfer was independently authorized/reviewed.",
    )


def build_interest_damages_finding(result: InterestClaimResult | None) -> MasterFinding | None:
    if result is None or (result.claimed_amount is None and result.period_start is None):
        return None

    legal_research_required = True  # every branch below requires verified law to resolve, never guessed here
    if result.maturity_date_after_period_start is True:
        legal_significance = (
            "The claimed interest period begins before a contractual maturity/return date found in the record. "
            "Whether interest for use of another's funds may properly run before a loan's own maturity date — "
            "as opposed to only from a later default date — is a legal question this system does not resolve."
        )
        strength = "HIGH"
    elif result.period_start_matches_earliest_payment:
        legal_significance = (
            "The claimed interest period begins on the date of the first payment itself. Whether interest may "
            "properly accrue from the transfer date, or only from a later date (e.g. demand or contractual "
            "maturity), is a legal question this system does not resolve."
        )
        strength = "MEDIUM"
    else:
        legal_significance = (
            "A claimed interest/damages period was identified in the case record, but this system found no "
            "contract maturity date or matching payment date to cross-reference it against."
        )
        strength = "MEDIUM"

    period_text = (
        f" for the period {result.period_start.isoformat()} to {result.period_end.isoformat()}"
        if result.period_start and result.period_end
        else ""
    )
    statement = (
        f"The claim includes an interest/damages figure"
        f"{f' of {result.claimed_amount}' if result.claimed_amount else ''}{period_text}."
    )

    return MasterFinding(
        id="interest_calculation:claim",
        category=FindingCategory.INTEREST_CALCULATION,
        title="Claimed interest/damages period requires legal verification",
        statement=statement,
        helps_side="neutral", hurts_side="neutral", strength=strength,
        confidence="Deterministic extraction from claim-document text; the legal conclusion is explicitly not resolved.",
        legal_significance=legal_significance,
        caveat="This system does not calculate or verify interest against unverified legal rules — see legal_research_required.",
        alternative_explanations=[
            "Interest may properly run from the transfer date if no contractual maturity governs the claim.",
            "Interest may only be due from a contractual default/maturity date, if one is established in the record.",
        ],
        what_would_strengthen=["Verified case law or statute confirming the correct accrual start date for this fact pattern."],
        what_would_weaken=["A contractual provision or verified legal rule confirming interest properly accrues from the transfer date."],
        recommended_action="Obtain verified legal research on the applicable accrual start date before relying on either interpretation.",
        legal_research_required=legal_research_required,
    )


def build_interest_table_finding(summary: InterestCalculationSummary) -> MasterFinding | None:
    """Surfaces the structured per-installment breakdown (Part 2) as its own
    finding, distinct from `build_interest_damages_finding`'s single-period
    reading — present together when a claim uses a per-installment table
    rather than one flat period. The claimed total is presented as the
    CLAIMANT's own stated figure (CLAIMANT_CALCULATION), never as a Legal-AI
    computed conclusion; per-row `arithmetic_check` results are an internal
    consistency check only, not a legal entitlement determination.
    """
    if summary.row_count == 0:
        return None
    mismatches = [r for r in summary.rows if r.arithmetic_check == "does_not_match_claimed"]
    statement = (
        f"The claim computes interest/damages across {summary.row_count} per-installment row(s)"
        f"{f', totaling {summary.claimed_interest_total} rub. as stated by the claimant' if summary.claimed_interest_total else ''}."
    )
    if summary.unparsed_row_count:
        statement += f" {summary.unparsed_row_count} additional row(s) could not be reliably parsed from the source document."
    caveats = [
        "This is the claimant's own stated calculation (CLAIMANT_CALCULATION), reproduced for review — not a "
        "Legal-AI determination of the legally correct amount (LEGAL_ENTITLEMENT requires verified legal review).",
    ]
    if mismatches:
        caveats.append(
            f"{len(mismatches)} row(s) where principal/rate/days were all identified do not reproduce the claimed "
            "row amount by simple arithmetic (LEGAL_AI_ARITHMETIC_CHECK) — worth independent verification."
        )
    return MasterFinding(
        id="interest_calculation:table",
        category=FindingCategory.INTEREST_CALCULATION,
        title="Per-installment interest/damages calculation",
        statement=statement,
        helps_side="neutral", hurts_side="neutral",
        strength="HIGH" if mismatches else "MEDIUM",
        confidence=(
            f"Deterministic extraction: {summary.row_count} row(s) parsed, {summary.unparsed_row_count} unparsed. "
            "See calculation_warnings for data-quality detail."
        ),
        legal_significance=(
            "A per-installment calculation should be checked row-by-row against the underlying payment evidence "
            "and applicable rate history."
        ),
        caveat=" ".join(caveats),
        missing_evidence=(
            ["Legible, unredacted copy of the interest calculation table for the rows this system could not parse."]
            if summary.unparsed_row_count
            else []
        ),
        recommended_action="Independently verify each row's principal, period, and rate against the underlying payment evidence.",
        legal_research_required=True,
    )


def build_notice_timeline_finding(result: NoticeTimelineResult) -> MasterFinding | None:
    if not result.tracking_report_present or result.final_status == "UNKNOWN":
        return None
    strength = "HIGH" if result.final_status in ("RETURNED", "NOTICE_LEFT") else "MEDIUM"
    return MasterFinding(
        id="notice_timeline:demand",
        category=FindingCategory.PROCEDURAL,
        title="Pre-suit demand delivery outcome",
        statement=result.final_status_explanation,
        helps_side="neutral", hurts_side="neutral", strength=strength,
        confidence=(
            f"Deterministic classification of a Russian Post tracking report "
            f"(tracking number {result.tracking_number or 'not identified'})."
        ),
        legal_significance=(
            "Whether pre-suit demand/notice was actually received may be relevant to compliance with any "
            "applicable pre-suit notice requirement and to when the addressee is deemed to have learned of the claim."
        ),
        caveat="Non-delivery of a demand letter does not by itself defeat a claim that does not require pre-suit notice as a condition.",
        legal_research_required=True,
    )


_TEMPORAL_ISSUE_TEMPLATES: dict[str, tuple[str, str, str]] = {
    # issue_type -> (title, statement_template, legal_significance)
    "interest_before_demand": (
        "Claimed interest accrual predates the demand letter",
        "The claimed interest period begins ({interest_start}) before the pre-suit demand letter ({demand_date}).",
        "Whether interest may properly accrue before any demand was made — as opposed to only from a demand or "
        "later default date — is a legal question this system does not resolve.",
    ),
    "demand_not_confirmed_received": (
        "Pre-suit demand not confirmed received",
        "The pre-suit demand letter dated {demand_date} does not, on this record, appear to have been "
        "confirmed as received by the addressee.",
        "May be relevant to whether pre-suit notice requirements were satisfied and to when the addressee is "
        "deemed to have known of the claim — this does not by itself resolve that legal question.",
    ),
    "interest_before_maturity": (
        "Claimed interest accrual predates contract maturity",
        "The claimed interest period begins ({interest_start}) before a contractual maturity/return date found "
        "in the record ({maturity}).",
        "Whether interest may properly run before a loan's own maturity date, as opposed to only from a later "
        "default date, is a legal question this system does not resolve.",
    ),
    "claim_filed_before_maturity": (
        "Claim filed before contract maturity",
        "The claim document's own stated date ({claim_date}) precedes a contractual maturity/return date found "
        "in the record ({maturity}).",
        "May raise a prematurity issue, subject to contract validity, any acceleration provisions, termination "
        "rights, and applicable law — this system does not resolve whether the claim was in fact premature.",
    ),
}


def build_temporal_issue_findings(issues: list[TemporalIssue]) -> list[MasterFinding]:
    findings = []
    for i, issue in enumerate(issues):
        template = _TEMPORAL_ISSUE_TEMPLATES.get(issue.issue_type)
        if template is None:
            continue
        title, statement_template, legal_significance = template
        date_kwargs = {k: v.isoformat() for k, v in issue.dates.items()}
        findings.append(
            MasterFinding(
                id=f"timing:{issue.issue_type}:{i}",
                category=FindingCategory.TIMING,
                title=title,
                statement=statement_template.format(**date_kwargs),
                helps_side="neutral", hurts_side="neutral", strength="HIGH",
                confidence="Deterministic date comparison over already-extracted case dates.",
                legal_significance=legal_significance,
                caveat="A timing observation alone does not resolve any legal question — see legal_significance.",
                legal_research_required=True,
            )
        )
    return findings


def build_timing_synthesis_finding(temporal_findings: list[MasterFinding]) -> MasterFinding | None:
    """Part 5(b): when 2+ independent timing observations co-occur, present
    ONE synthesized timing issue referencing each underlying finding, rather
    than leaving the lawyer to notice the connection across separate cards.
    """
    if len(temporal_findings) < 2:
        return None
    combined_statements = " ".join(f.statement for f in temporal_findings)
    return MasterFinding(
        id="synthesis:timing",
        category=FindingCategory.SYNTHESIS,
        title="Multiple timing observations together may raise a prematurity/accrual issue",
        statement=(
            f"{len(temporal_findings)} independent timing observations were identified in this case: "
            f"{combined_statements}"
        ),
        helps_side="neutral", hurts_side="neutral", strength="HIGH",
        confidence="Synthesis of independently-computed, deterministic timing observations — see synthesizes for each underlying finding.",
        legal_significance=(
            "Taken together, these timing observations may support a prematurity or accrual-date argument, "
            "subject to verified legal research — no single observation alone is dispositive."
        ),
        caveat=(
            "This synthesis combines independently-computed observations; it does not itself establish that "
            "any legal deadline was missed."
        ),
        legal_research_required=True,
        synthesizes=[f.id for f in temporal_findings],
    )


def build_credibility_synthesis_finding(
    allegation_types_present: set[AllegationType],
    pattern: PaymentPatternResult,
    relationship_findings: list[PartyRelationshipFinding],
    earliest_payment_date: date | None,
) -> MasterFinding | None:
    """Part 5(a) worked example: corporate relationship predating the
    payments + a repeated, similarly-described transfer pattern + a mistake/
    no-legal-basis allegation, combined into ONE synthesized credibility
    observation. Explicitly phrased as "may weaken ... warrants examination"
    — never "therefore the payment was not mistaken."
    """
    matched_types = allegation_types_present & _MISTAKE_LIKE_ALLEGATIONS
    if not pattern.is_significant or not matched_types or earliest_payment_date is None:
        return None

    predating_relationships = [
        f for f in relationship_findings
        if classify_relationship_timing(f.relationship_start, f.relationship_end, earliest_payment_date).status == "active_at_date"
    ]
    if not predating_relationships:
        return None

    relationship_names = ", ".join(sorted({f.related_party_name for f in predating_relationships}))
    type_labels = ", ".join(sorted(t.value for t in matched_types))
    return MasterFinding(
        id="synthesis:credibility",
        category=FindingCategory.SYNTHESIS,
        title="Documented relationship + repeated transfers may warrant scrutiny of the pleaded theory",
        statement=(
            f"A documented relationship with {relationship_names} predates the transfers in this case. Combined "
            f"with a repeated, similarly-described transfer pattern ({pattern.description}), this may weaken a "
            f"purely accidental-transfer explanation and warrants examination of the parties' actual knowledge "
            f"and course of dealing. This does not by itself establish that the pleaded theory ('{type_labels}') is false."
        ),
        helps_side="neutral", hurts_side="neutral", strength="HIGH",
        confidence="Synthesis of independently-computed corporate-relationship timing and payment-pattern signals.",
        legal_significance=(
            "A court may weigh a pre-existing relationship together with a repeated transfer pattern when "
            "assessing whether a mistake/no-legal-basis theory is credible on the full record."
        ),
        caveat=(
            "Corporate relationship status alone is not evidence of actual knowledge, and a repeated pattern "
            "does not itself disprove that each transfer was independently mistaken — each must still be "
            "assessed on its own facts."
        ),
        alternative_explanations=[
            "Each transfer could have been independently and separately mistaken, notwithstanding the relationship and pattern.",
        ],
        recommended_action=(
            "Obtain correspondence or internal records showing the relevant parties' actual knowledge and "
            "authorization for each transfer."
        ),
        legal_research_required=False,
        synthesizes=(
            ["theory_vs_conduct:payment_pattern"]
            + [f"corporate_relationship:{relationship_findings.index(f)}" for f in predating_relationships]
        ),
    )


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
    if FindingCategory.COURSE_OF_DEALING in categories_present:
        scenarios.append(
            CourtScenario(
                scenario=(
                    "Court finds an ongoing or renewed lending relationship between the parties spanning "
                    "multiple contractual references, rather than a single isolated or mistaken transaction."
                ),
                why_court_could_get_there=(
                    "Payments in the record reference more than one contractual date, weighing toward a "
                    "continuing relationship."
                ),
                facts_supporting=[f.title for f in findings if f.category == FindingCategory.COURSE_OF_DEALING],
                facts_against=[
                    "Multiple contractual references may equally reflect separate, unrelated transactions "
                    "rather than one continuing relationship."
                ],
            )
        )
    if FindingCategory.INTEREST_CALCULATION in categories_present:
        scenarios.append(
            CourtScenario(
                scenario="Court adopts a different interest/damages accrual start date than the one pleaded.",
                why_court_could_get_there=(
                    "The claimed interest period's start date has not been verified against a confirmed "
                    "legal rule or contractual maturity date."
                ),
                facts_supporting=[f.title for f in findings if f.category == FindingCategory.INTEREST_CALCULATION],
                facts_against=["The pleaded accrual date may be correct if supported by verified legal authority not yet obtained."],
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
    FindingCategory.COURSE_OF_DEALING: [
        "Do the multiple contractual references in the record reflect one continuing relationship or separate, unrelated agreements?",
        "Why does a later transfer reference a different contractual date than the earlier transfers?",
    ],
    FindingCategory.INTEREST_CALCULATION: [
        "On what legal basis does the claimed interest/damages period begin on the date stated, rather than any other date?",
    ],
    FindingCategory.PARTY_CONDUCT: [
        "Was each transfer independently authorized and reviewed, or were they treated as part of a single ongoing arrangement?",
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

    category_by_section: dict[str, list[FindingCategory]] = {
        "Основание перечислений / договорные отношения": [FindingCategory.CONTRACT_FORMATION, FindingCategory.COURSE_OF_DEALING],
        "Внутренние противоречия истца": [FindingCategory.CLAIM_CONTRADICTION, FindingCategory.PARTY_CONDUCT],
        "Проценты / убытки": [FindingCategory.INTEREST_CALCULATION],
        "Процессуальные вопросы": [FindingCategory.PROCEDURAL],
    }

    sections: list[DraftResponseSection] = []
    for section, argument in _RESPONSE_STRUCTURE_TEMPLATE:
        relevant_categories = category_by_section.get(section, [])
        relevant = [f for category in relevant_categories for f in by_category.get(category, [])]
        sections.append(
            DraftResponseSection(
                section=section, argument=argument, supporting_finding_ids=[f.id for f in relevant],
                caution="No findings currently support this section — do not overstate." if relevant_categories and not relevant else None,
            )
        )
    return sections
