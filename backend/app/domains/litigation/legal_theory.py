"""Legal Theory Layer (P1). Converts already-extracted, already-proven case
facts into candidate legal theories — but a candidate is NEVER labeled
LEGAL_THEORY on this module's own say-so. This module only computes the
deterministic FACT-PATTERN half (supporting facts, contradicting facts,
evidence gaps) from structured case data already produced elsewhere in this
package; it makes zero LLM calls and touches no legal text. The other half —
verifying that a real, verified legal authority actually supports the
theory — happens in `pipeline.py` via the existing `LegalResearchEngine`
(the same engine `app/domains/contracts/risk_verification.py` already uses
for exactly this kind of fail-closed verification), never reimplemented
here.

A `TheoryCandidate` is explicitly NOT a legal conclusion. It becomes a
`LegalTheoryResult` (see pipeline.py) only after that verification step, and
even then is classified LEGAL_THEORY only when the research engine returns
at least one VERIFIED citation. Anything less — no citation, a MOCK-sourced
citation, or the research engine's own "cannot conclude, no verified
authority" response — is classified COUNSEL_HYPOTHESIS. This module fails
closed by construction: it never emits a classification field at all,
leaving that entirely to the verification step.

Every check below is deliberately generic — keyed off structural shape
(payment counts, date ordering, amount comparisons, presence/absence of
notarization or signature language) rather than any case's specific
company names, amounts, or dates. The "alternative explanation" a
theory candidate carries is not decoration: real Russian civil litigation
routinely has more than one honest reading of the same fact pattern, and a
candidate that only ever argues for itself is not a fact-pattern
evaluation, it's advocacy — see contract_forensics.py's own discipline for
the same principle applied to contract-version mismatches.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class EvidenceGap:
    missing_fact: str
    why_it_matters: str
    could_be_proven_by: str
    # Qualitative, not a fabricated percentage: "critical" | "significant" | "moderate" | "minor"
    strengthens_theory_if_obtained: str


@dataclass
class TheoryCandidate:
    """The deterministic, zero-LLM half of a candidate legal theory. Never
    itself a legal conclusion — see module docstring.
    """

    name: str
    supporting_facts: list[str] = field(default_factory=list)
    contradicting_facts: list[str] = field(default_factory=list)
    alternative_explanations: list[str] = field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = field(default_factory=list)
    # A generic, jurisdiction-level legal question — deliberately never
    # mentions this case's party names, amounts, or dates, since it is sent
    # to the shared Legal Research Engine as a question of LAW, not of fact.
    research_question: str = ""
    # Whether the fact pattern even reaches the point of being worth
    # verifying against legal authority — e.g. a theory needing 2+ payments
    # with a case that has 0 payments has nothing to evaluate.
    preconditions_met: bool = True


@dataclass
class PaymentSignal:
    """The minimal payment shape this module needs — deliberately its own
    type rather than importing pipeline.py's MoneyFlowTransaction, keeping
    this module dependency-free like every other pure module in this package.
    """

    payment_date: date | None
    amount: str | None
    referenced_contract_date: date | None


@dataclass
class ContractSignal:
    """The minimal contract-terms shape this module needs — mirrors the
    relevant subset of contract_forensics.ContractVersionTerms.
    """

    document_title: str
    amounts: list[str]
    maturity_dates: list[str]
    formation_clause_present: bool
    signature_status: str
    notarized: bool


def _amount_to_float(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None


def evaluate_contract_formation_by_conduct(
    payments: list[PaymentSignal], contracts: list[ContractSignal]
) -> TheoryCandidate:
    """Part 3 of the P1 brief: independently evaluates whether the existing
    evidence can support "the contract was concluded/performed through the
    conduct of the parties" (Art. 432/434/438/807 GK RF territory) — without
    ever asserting the legal conclusion itself, and without injecting
    anything about what any particular golden-standard document argues.
    Every one of the 8 named factors is computed here, even when it comes
    back empty/neutral — an unlisted factor is not the same as a factor
    that was checked and found absent.
    """
    supporting: list[str] = []
    contradicting: list[str] = []
    gaps: list[EvidenceGap] = []

    dated_payments = sorted((p for p in payments if p.payment_date is not None), key=lambda p: p.payment_date)  # type: ignore[arg-type,return-value]

    # 1. Repeated payments.
    if len(payments) >= 2:
        supporting.append(f"{len(payments)} separate payments were made, rather than a single isolated transfer.")
    elif len(payments) == 1:
        contradicting.append(
            "Only one payment was found — a single transfer is weaker evidence of an ongoing performance "
            "relationship than a repeated pattern."
        )
    else:
        contradicting.append("No payments were found in the case record to evaluate a conduct-based performance theory against.")

    # 2. Common agreement reference.
    referenced_dates = {p.referenced_contract_date for p in payments if p.referenced_contract_date is not None}
    if len(referenced_dates) == 1:
        only_date = next(iter(referenced_dates)).isoformat()
        supporting.append(f"All payments that state a referenced agreement consistently cite the same date ({only_date}).")
    elif len(referenced_dates) > 1:
        date_list = ", ".join(sorted(d.isoformat() for d in referenced_dates))
        supporting.append(
            f"Payments reference {len(referenced_dates)} distinct agreement dates ({date_list}) — consistent with "
            "an evolving or renewed lending relationship, though this could equally reflect separate, unrelated arrangements."
        )
    else:
        contradicting.append("No payment states a referenced agreement date at all.")
    unreferenced_count = sum(1 for p in payments if p.referenced_contract_date is None)
    if unreferenced_count and payments:
        contradicting.append(f"{unreferenced_count} of {len(payments)} payment(s) state no referenced agreement at all.")

    # 3. Chronology — do payments follow (not precede) the earliest referenced agreement date?
    if referenced_dates and dated_payments:
        earliest_reference = min(referenced_dates)
        preceding_payments = [p for p in dated_payments if p.payment_date is not None and p.payment_date < earliest_reference]
        if preceding_payments:
            contradicting.append(
                f"{len(preceding_payments)} payment(s) predate the earliest referenced agreement date "
                f"({earliest_reference.isoformat()}) — performance before the referenced agreement existed is in "
                "tension with conduct affirming that agreement."
            )
        else:
            supporting.append(
                f"Every dated payment falls on or after the earliest referenced agreement date ({earliest_reference.isoformat()}) — "
                "consistent with (though not proof of) performance under that agreement's terms."
            )

    # 4. Amount inconsistencies between agreement drafts and transfers.
    contract_amounts = {a for c in contracts for a in c.amounts}
    transferred_amounts = {p.amount for p in payments if p.amount is not None}
    if contract_amounts and transferred_amounts:
        matching = contract_amounts & transferred_amounts
        if matching:
            supporting.append(f"{len(matching)} contract-stated amount(s) exactly match an amount actually transferred.")
        total_transferred = sum(v for a in transferred_amounts if (v := _amount_to_float(a)) is not None)
        mismatched_contract_amounts = [a for a in contract_amounts if _amount_to_float(a) != total_transferred]
        if mismatched_contract_amounts and not matching:
            contradicting.append(
                f"None of the contract-stated amount(s) ({', '.join(sorted(mismatched_contract_amounts))}) match the total actually "
                f"transferred ({total_transferred:.2f}) — this may reflect an agreement whose terms were never finalized, "
                "or partial/staged performance under a larger facility; the mismatch alone does not establish either reading."
            )
    elif contract_amounts and not transferred_amounts:
        contradicting.append("Contract document(s) state amount(s), but no corresponding transferred amount was found to compare against.")

    # 5. Signatures / missing signatures.
    signed = [c for c in contracts if c.signature_status == "confirmed_signed"]
    unsigned_or_unknown = [c for c in contracts if c.signature_status != "confirmed_signed"]
    if signed:
        supporting.append(f"{len(signed)} contract document(s) have a confirmed signed copy in the record.")
    if unsigned_or_unknown and contracts:
        contradicting.append(
            f"{len(unsigned_or_unknown)} of {len(contracts)} contract document(s) in the record have no confirmed signature — "
            "absence of a signature does not itself defeat a conduct-based theory, but it removes the most direct evidence of assent."
        )
        gaps.append(
            EvidenceGap(
                missing_fact="A confirmed, signed copy of the referenced agreement.",
                why_it_matters=(
                    "Direct signature evidence is the strongest, least inference-dependent proof of assent — its "
                    "absence is exactly why a conduct-based theory is being considered at all."
                ),
                could_be_proven_by=(
                    "The signed original or a certified copy from either party's own records, or a notarized "
                    "version if one exists."
                ),
                strengthens_theory_if_obtained="critical",
            )
        )

    # 6. Later notarized agreement.
    notarized_contracts = [c for c in contracts if c.notarized]
    if notarized_contracts:
        supporting.append(
            f"{len(notarized_contracts)} contract document(s) in the record are notarized — a notarized instrument is materially "
            "stronger evidence of the parties' assent than an unsigned draft, independent of any conduct-based argument."
        )
    elif contracts:
        contradicting.append(
            "No contract document in the record shows notarization language — formation must rest on "
            "conduct/signature evidence alone."
        )

    # 7. Later payment behavior — payments continuing after a later-dated agreement.
    if len(referenced_dates) > 1:
        later_reference = max(referenced_dates)
        payments_after_later = [p for p in dated_payments if p.payment_date is not None and p.payment_date >= later_reference]
        if payments_after_later:
            supporting.append(
                f"{len(payments_after_later)} payment(s) were made on or after the later referenced agreement date "
                f"({later_reference.isoformat()}), consistent with continued performance rather than a one-off transfer."
            )

    # 8. Alternative explanations — always present, never omitted.
    alternatives = [
        "The payments could instead reflect an ongoing, never-finalized negotiation rather than a concluded agreement — "
        "repeated transfers do not themselves prove mutual assent to specific terms.",
        "A referenced agreement date in a payment's own stated purpose is the payer's own characterization at the time — "
        "it is evidence of the payer's belief or intent, not independent proof that the counterparty accepted those terms.",
    ]
    if unsigned_or_unknown:
        alternatives.append(
            "Without a signed or notarized instrument, the payments could equally reflect advance/anticipatory transfers "
            "made in the expectation of a future agreement that was never actually reached."
        )

    preconditions_met = len(payments) >= 1

    return TheoryCandidate(
        name="Contract formation/performance through the conduct of the parties",
        supporting_facts=supporting,
        contradicting_facts=contradicting,
        alternative_explanations=alternatives,
        evidence_gaps=gaps,
        research_question=(
            "Under Russian civil law, when a written loan agreement between legal entities was never signed by both "
            "parties, under what conditions (if any) can the agreement nonetheless be treated as concluded or performed "
            "through the conduct of the parties — for example repeated transfers referencing the agreement's terms, "
            "and a subsequent notarized agreement on matching terms? What evidentiary standard applies, and what are the "
            "leading statutory provisions and controlling interpretations?"
        ),
        preconditions_met=preconditions_met,
    )


def evaluate_corporate_relationship_gaps(
    *,
    counterparty_relationship_found: bool,
    subject_own_registry_document_present: bool,
    counterparty_name: str,
    subject_name: str,
) -> list[EvidenceGap]:
    """Part 4 of the P1 brief: corporate-relationship reasoning restricted to
    independent evidence only. When a relationship is found on ONE side
    (e.g. an individual's registry-confirmed role at the counterparty) but
    the SAME individual's role at the case's own client/claimant side has no
    supporting document in the case record, this produces an explicit gap
    rather than assuming or inventing the missing half.
    """
    if not counterparty_relationship_found or subject_own_registry_document_present:
        return []
    return [
        EvidenceGap(
            missing_fact=(
                f"An official registry extract (e.g. EGRUL) for {subject_name} showing whether the same "
                "individual holds a role there."
            ),
            why_it_matters=(
                f"A relationship was found showing an individual's role at {counterparty_name}, but without "
                f"{subject_name}'s own registry document there is no independently-verified evidence of that "
                f"individual's role (if any) at {subject_name} — a dual-role affiliation argument requires "
                "evidence on BOTH sides, not one."
            ),
            could_be_proven_by=(
                f"An EGRUL (or equivalent official registry) extract for {subject_name}, dated at or near the "
                "events in dispute."
            ),
            strengthens_theory_if_obtained="significant",
        )
    ]
