"""Client-facing Case Result Summary — a template/deterministic synthesis
layer over already-computed E1-E4 litigation data (CaseFact, CaseAllegation,
CasePaymentOrder, ClaimEvidenceContradiction, CaseContradiction,
MoneyFlowSummary). Zero LLM calls, same discipline as every other module in
this package.

This is NOT the strategist (E5/E6 — discovery planning, opponent modeling,
counterargument generation, contract-formation verdicts): every sentence
here is either a direct readout of persisted data or one of a small set of
template conclusions, each gated on a real, computed precondition. Nothing
here ever states that a contract was or was not concluded — the strongest
claim this module makes is "this evidence creates a basis to further verify
X", matching the caveat discipline already established by
contradiction_detector.py's CLAIM_VS_EVIDENCE rule.

Missing-evidence detection is deliberately conservative: an item is only
listed when the case genuinely has zero documents of the relevant role (or,
for repayment evidence, zero payments flowing in the reverse direction).
Phrasing is always "не обнаружено среди загруженных материалов" — a
statement about what has been uploaded so far, never a claim that the
document doesn't exist.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from app.domains.litigation.contradiction_detector import ClaimEvidenceContradiction, ContradictionCandidate
from app.models.matters import CaseDocumentRole, ContradictionType

if TYPE_CHECKING:
    # Deferred to avoid a circular import — pipeline.py imports this module
    # to build the summary; only the type name is needed here, never at runtime.
    from app.domains.litigation.pipeline import MoneyFlowSummary

_KB_WARNING = (
    "Правовая квалификация пока ограничена: система выявила доказательственные факты и противоречия, "
    "но не подтверждает окончательную правовую позицию без проверенных норм права."
)


@dataclass
class CaseSnapshot:
    party_names: list[str]
    document_count: int
    payment_count: int
    total_amount: str
    key_dates: list[tuple[date | None, str]]


@dataclass
class KeyFinding:
    severity: str  # HIGH | MEDIUM
    statement: str
    source_document_id: uuid.UUID
    source_document_title: str
    page_number: int | None
    excerpt: str
    confidence: str
    caveat: str | None = None


@dataclass
class MissingEvidenceItem:
    priority: str  # CRITICAL
    description: str
    why_it_matters: str
    source_document_id: uuid.UUID | None = None
    source_document_title: str | None = None


@dataclass
class NextBestAction:
    priority: int
    action: str
    why: str


@dataclass
class CaseResultSummary:
    case_snapshot: CaseSnapshot
    key_findings: list[KeyFinding]
    money_flow: MoneyFlowSummary
    what_this_may_mean: list[str]
    missing_critical_evidence: list[MissingEvidenceItem]
    next_best_actions: list[NextBestAction]
    legal_kb_warning: str | None


# --- Contract signature status (fix for the production validation gap: a
# CONTRACT-role document's mere presence was previously treated as if the
# signed-copy question were resolved, even when the document's own text
# says it's an unsigned draft). Three-state, computed from the CONTRACT-role
# document(s)' own text via bounded, conservative regex — never inferred
# from role presence alone. No extractor in this codebase currently detects
# POSITIVE signature evidence beyond the narrow confirmations below, so
# "confirmed_signed" only fires on an explicit, unambiguous statement; the
# default for an ordinary (unmarked) contract document is "unknown", never
# a silent "signed".
_DRAFT_UNSIGNED_PATTERN = re.compile(
    r"проект\s+договора"
    r"|черновик"
    r"|не\s+являет[а-я]*\s+подписанным\s+экземпляром"
    r"|не\s+подписан[а-я]*"
    r"|подписанный\s+экземпляр\s+не\s+предоставлен",
    re.IGNORECASE,
)
_SIGNED_CONFIRMATION_PATTERN = re.compile(
    r"договор\s+подписан[а-я]*\s+сторонами"
    r"|подписанный\s+экземпляр\s+договора\s+прилагается"
    r"|стороны\s+подписали\s+договор",
    re.IGNORECASE,
)


def _classify_contract_signature(
    contract_documents: list[tuple[uuid.UUID, str, str]],
) -> tuple[str, uuid.UUID | None, str | None]:
    """contract_documents: (document_id, title, extracted_text) for every
    CONTRACT-role CaseDocument. Returns (status, causing_document_id,
    causing_document_title) — status is one of "no_contract_document",
    "unsigned_or_draft", "confirmed_signed", "unknown". Draft/unsigned
    indicators are checked before signed-confirmation ones, so a document
    that (contradictorily) contains both is conservatively treated as
    unsigned/draft rather than signed.
    """
    if not contract_documents:
        return "no_contract_document", None, None
    for document_id, title, text in contract_documents:
        if text and _DRAFT_UNSIGNED_PATTERN.search(text):
            return "unsigned_or_draft", document_id, title
    for document_id, title, text in contract_documents:
        if text and _SIGNED_CONFIRMATION_PATTERN.search(text):
            return "confirmed_signed", document_id, title
    first_id, first_title, _ = contract_documents[0]
    return "unknown", first_id, first_title


_NO_CONTRACT_DOCUMENT_ITEM = MissingEvidenceItem(
    priority="CRITICAL",
    description="Подтверждённый подписанный экземпляр договора не обнаружен среди загруженных материалов.",
    why_it_matters="Без подписанного экземпляра или подтверждения его направления факт согласования условий займа остаётся недоказанным.",
)
_UNKNOWN_SIGNATURE_ITEM = MissingEvidenceItem(
    priority="CRITICAL",
    description="Подтверждённый подписанный экземпляр договора не обнаружен среди загруженных материалов.",
    why_it_matters="Прикреплённый договорный документ не содержит однозначного подтверждения подписания сторонами.",
)


def _draft_contract_item(document_id: uuid.UUID, document_title: str) -> MissingEvidenceItem:
    return MissingEvidenceItem(
        priority="CRITICAL",
        description=(
            f"Прикреплённый договорный документ («{document_title}») по собственному тексту является проектом "
            "или содержит указание на отсутствие подписи — подтверждённый подписанный экземпляр договора не "
            "обнаружен среди загруженных материалов."
        ),
        why_it_matters=(
            "Без подписанного экземпляра или подтверждения его направления факт согласования условий займа "
            "остаётся недоказанным."
        ),
        source_document_id=document_id,
        source_document_title=document_title,
    )


def _signed_contract_missing_item(
    status: str, document_id: uuid.UUID | None, document_title: str | None
) -> MissingEvidenceItem | None:
    if status == "no_contract_document":
        return _NO_CONTRACT_DOCUMENT_ITEM
    if status == "unsigned_or_draft":
        assert document_id is not None and document_title is not None  # guaranteed by _classify_contract_signature
        return _draft_contract_item(document_id, document_title)
    if status == "unknown":
        return _UNKNOWN_SIGNATURE_ITEM
    return None  # confirmed_signed — the one case where the item is genuinely resolved


_CORRESPONDENCE_ITEM = MissingEvidenceItem(
    priority="CRITICAL",
    description=(
        "Переписка сторон о согласовании суммы, процентов и срока возврата займа, а также переписка "
        "после перечисления денежных средств — не обнаружена среди загруженных материалов."
    ),
    why_it_matters=(
        "Такая переписка — один из немногих источников, способных напрямую подтвердить или опровергнуть "
        "версию о существовании договорных отношений."
    ),
)
_ACT_ITEM = MissingEvidenceItem(
    priority="CRITICAL",
    description=(
        "Акты сверки взаиморасчётов или иные документы, фиксирующие признание задолженности, — "
        "не обнаружены среди загруженных материалов."
    ),
    why_it_matters="Признание задолженности контрагентом существенно повлияло бы на оценку отношений сторон.",
)
_ACCOUNTING_ITEM = MissingEvidenceItem(
    priority="CRITICAL",
    description="Документы бухгалтерского учёта, подтверждающие отражение операции у сторон, — не обнаружены среди загруженных материалов.",
    why_it_matters="Бухгалтерское отражение операции — независимый источник, способный подтвердить характер перечисления.",
)
_REPAYMENT_ITEM = MissingEvidenceItem(
    priority="CRITICAL",
    description="Документы о возврате или частичном возврате денежных средств — не обнаружены среди загруженных материалов.",
    why_it_matters="Наличие или отсутствие возврата средств напрямую влияет на оценку версии неосновательного обогащения либо займа.",
)


def _build_missing_evidence(
    roles_present: set[CaseDocumentRole],
    payment_directions: set[tuple[str, str]],
    signature_status: str,
    signature_document_id: uuid.UUID | None,
    signature_document_title: str | None,
) -> list[MissingEvidenceItem]:
    items: list[MissingEvidenceItem] = []
    signed_item = _signed_contract_missing_item(signature_status, signature_document_id, signature_document_title)
    if signed_item is not None:
        items.append(signed_item)
    if CaseDocumentRole.CORRESPONDENCE not in roles_present:
        items.append(_CORRESPONDENCE_ITEM)
    if CaseDocumentRole.ACT not in roles_present:
        items.append(_ACT_ITEM)
    if CaseDocumentRole.ACT not in roles_present and CaseDocumentRole.EXPERT_REPORT not in roles_present:
        items.append(_ACCOUNTING_ITEM)
    # Only two directions means money is known to have flowed both ways; one
    # direction (or none) means no evidence of any repayment was found.
    if len(payment_directions) <= 1:
        items.append(_REPAYMENT_ITEM)
    return items


def _build_what_this_may_mean(
    claim_evidence_contradictions: list[ClaimEvidenceContradiction],
    signature_status: str,
    contract_amount_candidates: list[str],
    money_flow_total: str,
    has_multi_payment_same_contract_date: bool,
) -> list[str]:
    conclusions: list[str] = []
    if claim_evidence_contradictions:
        conclusions.append(
            "Данные документы создают основание дополнительно проверять версию о существовании договорных "
            "отношений между сторонами."
        )
        conclusions.append(
            "Назначение платежа само по себе не доказывает заключение договора — требуется дополнительная "
            "проверка иных обстоятельств и документов."
        )
    # Never "договор не подписан" as a flat statement here — signature_status
    # being anything other than "confirmed_signed" means the question is
    # open, not that the contract IS unsigned (see _classify_contract_signature).
    if signature_status != "confirmed_signed":
        conclusions.append("Отсутствие подтверждённого подписанного экземпляра договора остаётся существенным неразрешённым вопросом.")
    for contract_amount in contract_amount_candidates:
        if contract_amount != money_flow_total:
            conclusions.append(
                f"Сумма, упомянутая в договорном документе ({contract_amount}), не совпадает с фактически "
                f"перечисленной суммой ({money_flow_total}) — это расхождение требует отдельного объяснения."
            )
    if has_multi_payment_same_contract_date:
        conclusions.append(
            "Несколько платежей ссылаются на одну и ту же дату договора, однако являются ли они частью одного "
            "обязательства или разных оснований — по представленным документам однозначно не установлено."
        )
    return conclusions


def _build_next_best_actions(
    missing_items: list[MissingEvidenceItem],
    claim_evidence_contradictions: list[ClaimEvidenceContradiction],
    money_flow: MoneyFlowSummary,
) -> list[NextBestAction]:
    actions: list[NextBestAction] = []
    if _CORRESPONDENCE_ITEM in missing_items and claim_evidence_contradictions:
        actions.append(
            NextBestAction(
                priority=1,
                action=(
                    "Запросить и поднять переписку сторон за период вокруг даты договора — сообщения, где "
                    "обсуждаются сумма, проценты, срок возврата и направление договора."
                ),
                why=(
                    "Переписка — практически единственный источник, способный напрямую подтвердить или "
                    "опровергнуть версию о существовании договорных отношений."
                ),
            )
        )
    if _ACCOUNTING_ITEM in missing_items:
        actions.append(
            NextBestAction(
                priority=len(actions) + 1,
                action="Проверить бухгалтерское отражение перечислений у обеих сторон.",
                why="Бухгалтерский учёт операции — независимое от переписки и пояснений сторон подтверждение характера перечисления.",
            )
        )
    if money_flow.transaction_count > 1:
        actions.append(
            NextBestAction(
                priority=len(actions) + 1,
                action="Сверить все платёжные поручения и определить, относятся ли они к одному договору или к разным основаниям.",
                why=(
                    "Совпадение указанной в платежах даты договора не является доказательством того, что все "
                    "платежи относятся к одному обязательству."
                ),
            )
        )
    return actions[:3]


def build_case_result_summary(
    *,
    party_names: list[str],
    document_count: int,
    roles_present: set[CaseDocumentRole],
    key_dates: list[tuple[date | None, str]],
    document_titles: dict[uuid.UUID, str],
    claim_evidence_contradictions: list[ClaimEvidenceContradiction],
    case_contradictions: list[ContradictionCandidate],
    money_flow: MoneyFlowSummary,
    contract_amount_candidates: list[str],
    contract_documents: list[tuple[uuid.UUID, str, str]],
    kb_is_empty: bool,
) -> CaseResultSummary:
    case_snapshot = CaseSnapshot(
        party_names=party_names,
        document_count=document_count,
        payment_count=money_flow.transaction_count,
        total_amount=money_flow.total_amount,
        key_dates=key_dates,
    )

    key_findings: list[KeyFinding] = []
    for c in claim_evidence_contradictions:
        key_findings.append(
            KeyFinding(
                severity="HIGH",
                statement=c.reason,
                source_document_id=c.evidence_document_id,
                source_document_title=document_titles.get(c.evidence_document_id, "(deleted)"),
                page_number=c.evidence_page,
                excerpt=c.evidence_excerpt,
                confidence=c.confidence,
                caveat=c.caveat,
            )
        )
    for cc in case_contradictions:
        if cc.contradiction_type not in (ContradictionType.DATE_MISMATCH, ContradictionType.AMOUNT_MISMATCH):
            continue
        evidence = cc.fact_a.evidence[0] if cc.fact_a.evidence else None
        key_findings.append(
            KeyFinding(
                severity="MEDIUM",
                statement=cc.description,
                source_document_id=evidence.document_id if evidence else uuid.UUID(int=0),
                source_document_title=document_titles.get(evidence.document_id, "(deleted)") if evidence else "(unknown)",
                page_number=evidence.page_number if evidence else None,
                excerpt=evidence.excerpt if evidence else "",
                confidence="Deterministic fact comparison, no model inference.",
            )
        )
    key_findings = key_findings[:5]

    signature_status, signature_document_id, signature_document_title = _classify_contract_signature(contract_documents)

    payment_directions = {(t.payer, t.recipient) for t in money_flow.transactions if t.payer and t.recipient}
    missing_items = _build_missing_evidence(
        roles_present, payment_directions, signature_status, signature_document_id, signature_document_title
    )

    has_multi_payment_same_date = any(count > 1 for count in money_flow.referenced_contract_dates.values())
    what_this_may_mean = _build_what_this_may_mean(
        claim_evidence_contradictions, signature_status, contract_amount_candidates, money_flow.total_amount, has_multi_payment_same_date
    )

    next_best_actions = _build_next_best_actions(missing_items, claim_evidence_contradictions, money_flow)

    return CaseResultSummary(
        case_snapshot=case_snapshot,
        key_findings=key_findings,
        money_flow=money_flow,
        what_this_may_mean=what_this_may_mean,
        missing_critical_evidence=missing_items,
        next_best_actions=next_best_actions,
        legal_kb_warning=_KB_WARNING if kb_is_empty else None,
    )
