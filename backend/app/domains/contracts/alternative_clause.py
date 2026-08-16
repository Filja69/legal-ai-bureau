"""AlternativeClause generation — brief §37. Template-based standard
Russian contract drafting patterns per risk type — not LLM-generated
prose, and explicitly NOT presented as ready-to-sign text: every alternative
carries `change_reason` + is routed through the redline/review flow, which
flags human lawyer review before use (LEGAL-PRD.md §6 escalation policy).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domains.contracts.risk_verification import VerifiedRisk

_TEMPLATES: dict[str, tuple[str, str]] = {
    # detector name -> (proposed_text_template, change_reason)
    "liability": (
        "Ответственность Стороны по настоящему Договору ограничена суммой, "
        "фактически уплаченной другой Стороне по Договору за 12 (двенадцать) "
        "месяцев, предшествующих событию, повлекшему ответственность.",
        "Установлен предел (cap) ответственности вместо неограниченной ответственности.",
    ),
    "termination": (
        "Каждая из Сторон вправе отказаться от исполнения настоящего Договора, "
        "письменно уведомив об этом другую Сторону не менее чем за 10 (десять) "
        "рабочих дней до предполагаемой даты расторжения.",
        "Введен срок предварительного уведомления вместо расторжения без уведомления.",
    ),
    "penalty": (
        "В случае нарушения Стороной своих обязательств по настоящему Договору "
        "виновная Сторона уплачивает другой Стороне неустойку в размере, "
        "указанном в настоящем пункте, независимо от того, какая из Сторон "
        "допустила нарушение.",
        "Неустойка сделана взаимной (симметричной) вместо односторонней.",
    ),
    "indemnity": (
        "Сторона возмещает другой Стороне подтвержденный документально реальный "
        "ущерб, причиненный нарушением настоящего Договора. Возмещение "
        "упущенной выгоды и косвенных убытков настоящим Договором не "
        "предусмотрено, если иное прямо не согласовано Сторонами.",
        "Объем возмещения ограничен реальным ущербом вместо неограниченного "
        "возмещения, включая косвенные убытки.",
    ),
}


@dataclass
class AlternativeClauseDraft:
    proposed_text: str
    change_reason: str
    legal_basis: str | None
    risk_reduction: str  # "eliminates" | "reduces" | "mitigates"


def propose_alternative(verified_risk: VerifiedRisk) -> AlternativeClauseDraft | None:
    template = _TEMPLATES.get(verified_risk.candidate.detector)
    if template is None or verified_risk.candidate.clause_index is None:
        return None

    proposed_text, change_reason = template
    risk_reduction = "reduces" if verified_risk.verification_status.value == "unverified" else "mitigates"
    return AlternativeClauseDraft(
        proposed_text=proposed_text,
        change_reason=change_reason,
        legal_basis=verified_risk.legal_basis,
        risk_reduction=risk_reduction,
    )
