"""Contract Forensics — per-document structured term extraction for every
CONTRACT-role document in a case, plus a version-comparison matrix. Pure
functions, no DB, no LLM — same discipline as every other module in this
package. Reuses `app.domains.shared.legal_patterns` (the same AMOUNT/DATE
regex already used by `fact_extractor.py`) rather than a second, drifting
copy, and reuses `case_result_summary.py`'s signature-status classifier
rather than a second signature-detection heuristic.

Never concludes which version is "the" contract or that a contract was
concluded — a case with two differently-valued contract drafts is reported
as a MISMATCH with an explanation that cuts both ways (see
`build_contract_mismatch_finding`'s docstring), never resolved in either
party's favor.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from app.domains.litigation.case_result_summary import _classify_contract_signature
from app.domains.shared.legal_patterns import AMOUNT, DATE_NUMERIC, DATE_WORDY

_INTEREST_RATE_PATTERN = re.compile(r"(\d{1,2}(?:[.,]\d+)?)\s*\(?[а-яё]*\)?\s*процент[а-яё]*\s+годовых", re.IGNORECASE)
_FORMATION_CLAUSE_PATTERN = re.compile(r"считается\s+заключ[её]нн?ым\s+с\s+момента", re.IGNORECASE)
_MATURITY_CONTEXT_PATTERN = re.compile(r"(?:возврат[а-яё]*|срок[а-яё]*\s+до|обязан[а-яё]*\s+вернуть)[^.]{0,60}", re.IGNORECASE)


def _normalize_amount(raw: str) -> str | None:
    match = re.match(r"([\d\s]+)(?:[.,](\d{2}))?", raw)
    if not match:
        return None
    integer_part = match.group(1).replace(" ", "").replace("\xa0", "")
    if not integer_part.isdigit():
        return None
    fractional = match.group(2) or "00"
    return f"{int(integer_part)}.{fractional}"


@dataclass
class ContractVersionTerms:
    document_id: uuid.UUID
    document_title: str
    amounts: list[str] = field(default_factory=list)  # normalized decimal strings, in document order
    interest_rate: str | None = None
    maturity_dates: list[str] = field(default_factory=list)  # raw matched text, not normalized (mixed numeric/wordy formats)
    formation_clause_present: bool = False
    signature_status: str = "unknown"  # confirmed_signed | unsigned_or_draft | unknown


def extract_contract_terms(document_id: uuid.UUID, document_title: str, text: str) -> ContractVersionTerms:
    amounts = []
    for m in AMOUNT.finditer(text):
        normalized = _normalize_amount(m.group(0))
        if normalized and normalized not in amounts:
            amounts.append(normalized)

    rate_match = _INTEREST_RATE_PATTERN.search(text)
    interest_rate = f"{rate_match.group(1)}%" if rate_match else None

    maturity_dates: list[str] = []
    for context_match in _MATURITY_CONTEXT_PATTERN.finditer(text):
        window = text[context_match.start() : context_match.end() + 40]
        date_match = DATE_NUMERIC.search(window) or DATE_WORDY.search(window)
        if date_match and date_match.group(0) not in maturity_dates:
            maturity_dates.append(date_match.group(0))

    formation_clause_present = bool(_FORMATION_CLAUSE_PATTERN.search(text))

    status, _sig_doc_id, _sig_title = _classify_contract_signature([(document_id, document_title, text)])

    return ContractVersionTerms(
        document_id=document_id, document_title=document_title, amounts=amounts, interest_rate=interest_rate,
        maturity_dates=maturity_dates, formation_clause_present=formation_clause_present, signature_status=status,
    )


def build_contract_version_matrix(
    contract_documents: list[tuple[uuid.UUID, str, str]],
) -> list[ContractVersionTerms]:
    return [extract_contract_terms(doc_id, title, text) for doc_id, title, text in contract_documents]


def contract_amount_mismatch(matrix: list[ContractVersionTerms], money_flow_total: str) -> bool:
    """True only when at least one contract states an amount that matches
    NONE of the money-flow total or any other contract's amount — a single
    shared figure across versions/payments is not a mismatch.
    """
    all_amounts = {a for terms in matrix for a in terms.amounts}
    if not all_amounts:
        return False
    return money_flow_total not in all_amounts or len(all_amounts) > 1
