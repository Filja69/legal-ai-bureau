"""ContractRiskDetector — brief §17-21. Deliberately NOT one giant prompt:
twelve small, independently-testable, rule-based detectors, each producing
`RiskCandidate` objects with deterministic severity inputs (app/domains/
contracts/severity.py computes the actual severity band). Every candidate
carries a `clause_index` (or None for a missing-clause finding) so the
final `ContractRisk` row can always cite "Пункт 7.3", never a vague
"the contract has a liability risk" (brief §12).

Classification defaults to structural/commercial categories (HIGH_RISK,
UNFAVORABLE, AMBIGUOUS, MISSING_PROTECTION) — a detector never assigns
ILLEGAL or UNENFORCEABLE on its own; only the Legal Research verification
stage (app/domains/contracts/risk_verification.py) may upgrade a
classification, and only when research actually supports it (brief §27, §54).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domains.contracts.contract_profile import analyze_coverage
from app.domains.contracts.severity import SeverityInputs
from app.domains.contracts.structure_extractor import ExtractedClause
from app.models.contracts import ClauseType, ContractType, RiskCategory, RiskClassification, RiskType


@dataclass
class RiskCandidate:
    detector: str
    risk_type: RiskType
    category: RiskCategory
    classification: RiskClassification
    title: str
    description: str
    why_it_matters: str
    severity_inputs: SeverityInputs
    clause_index: int | None = None
    research_question: str | None = None  # if set, this candidate should be sent through Legal Research (brief §24-25)


class RiskDetector(Protocol):
    name: str

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]: ...


# --- helpers shared across detectors ---

_UNCAPPED_LIABILITY_MARKERS = ["не ограничивается", "в полном объеме", "без ограничения ответственности"]
_LIABILITY_CAP_MARKERS = ["не более", "ограничена суммой", "не превышает", "предел ответственности"]
_NO_NOTICE_TERMINATION_MARKERS = ["без уведомления", "в любое время", "без объяснения причин", "без предварительного уведомления"]
_NOTICE_PERIOD_MARKERS = ["уведомив", "письменного уведомления за", "предварительного уведомления за"]
_AMBIGUOUS_MARKERS = ["по возможности", "в разумный срок", "при необходимости", "по мере необходимости", "надлежащим образом"]
_BROAD_INDEMNITY_MARKERS = ["включая косвенные", "любые убытки", "все без исключения убытки", "включая упущенную выгоду"]
_FULL_PREPAYMENT_MARKERS = ["100% предоплат", "полная предоплата", "стопроцентная предоплата"]
_FOREIGN_JURISDICTION_MARKERS = [
    "лондонский международный третейский суд", "международный коммерческий арбитраж",
    "право англии и уэльса", "law of england",
]

_SYMMETRIC_OBLIGATION_MARKERS = ["стороны обяз", "обе стороны", "каждая из сторон", "все стороны"]
_SPECIFIC_ROLE_MARKERS = [
    "заказчик", "исполнитель", "поставщик", "покупатель", "арендодатель", "арендатор", "лицензиар", "лицензиат",
]


_MIN_SUBSTANTIVE_LENGTH = 25  # below this, a "clause" is almost certainly a bare heading, not real obligation text


def _clauses_of_type(clauses: list[ExtractedClause], clause_type: ClauseType) -> list[tuple[int, ExtractedClause]]:
    return [
        (i, c) for i, c in enumerate(clauses)
        if c.clause_type == clause_type and len(c.normalized_text) >= _MIN_SUBSTANTIVE_LENGTH
    ]


def _contains_any(text: str, markers: list[str]) -> bool:
    lowered = text.lower()
    return any(m in lowered for m in markers)


class MissingClauseDetector:
    name = "missing_clause"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        coverage = analyze_coverage(clauses, contract_type)
        candidates = []
        for clause_type in coverage.missing_required:
            candidates.append(
                RiskCandidate(
                    detector=self.name, risk_type=RiskType.MISSING_PROTECTION, category=RiskCategory.LEGAL,
                    classification=RiskClassification.MISSING_PROTECTION,
                    title=f"Отсутствует пункт: {clause_type.value}",
                    description=f"В договоре не обнаружен пункт типа '{clause_type.value}', ожидаемый для договоров данного типа.",
                    why_it_matters=(
                        "Отсутствие данного условия оставляет вопрос неурегулированным договором и может привести к применению "
                        "диспозитивных норм закона, которые не всегда выгодны стороне."
                    ),
                    severity_inputs=SeverityInputs(legal_impact=60, financial_impact=40, probability=50, scope=50, irreversibility=20),
                    clause_index=None,
                )
            )
        for clause_type in coverage.missing_recommended:
            candidates.append(
                RiskCandidate(
                    detector=self.name, risk_type=RiskType.MISSING_PROTECTION, category=RiskCategory.COMMERCIAL,
                    classification=RiskClassification.MISSING_PROTECTION,
                    title=f"Рекомендуемый пункт отсутствует: {clause_type.value}",
                    description=f"Пункт типа '{clause_type.value}' отсутствует, хотя обычно рекомендуется для договоров данного типа.",
                    why_it_matters="Не критично, но снижает предсказуемость исполнения договора.",
                    severity_inputs=SeverityInputs(legal_impact=20, financial_impact=15, probability=30, scope=30, irreversibility=10),
                    clause_index=None,
                )
            )
        return candidates


class AmbiguityDetector:
    name = "ambiguity"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        candidates = []
        for i, clause in enumerate(clauses):
            if _contains_any(clause.normalized_text, _AMBIGUOUS_MARKERS):
                candidates.append(
                    RiskCandidate(
                        detector=self.name, risk_type=RiskType.AMBIGUITY, category=RiskCategory.LEGAL,
                        classification=RiskClassification.AMBIGUOUS,
                        title="Неопределенная формулировка",
                        description=f"Пункт {clause.clause_number or i} содержит оценочную формулировку без точных критериев.",
                        why_it_matters="Оценочные формулировки создают почву для споров о толковании условия.",
                        severity_inputs=SeverityInputs(legal_impact=30, financial_impact=15, probability=40, scope=20, irreversibility=10),
                        clause_index=i,
                    )
                )
        return candidates


class LiabilityDetector:
    name = "liability"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        candidates = []
        for i, clause in _clauses_of_type(clauses, ClauseType.LIABILITY):
            has_uncapped = _contains_any(clause.normalized_text, _UNCAPPED_LIABILITY_MARKERS)
            has_cap = _contains_any(clause.normalized_text, _LIABILITY_CAP_MARKERS)
            if has_uncapped or not has_cap:
                candidates.append(
                    RiskCandidate(
                        detector=self.name, risk_type=RiskType.UNLIMITED_LIABILITY, category=RiskCategory.FINANCIAL,
                        classification=RiskClassification.HIGH_RISK,
                        title="Ответственность не ограничена",
                        description=f"Пункт {clause.clause_number or i} не содержит предела (cap) ответственности стороны.",
                        why_it_matters=(
                            "Неограниченная ответственность означает потенциально неограниченный финансовый риск при нарушении договора."
                        ),
                        severity_inputs=SeverityInputs(
                            legal_impact=40, financial_impact=80 if has_uncapped else 55,
                            probability=35, scope=60, irreversibility=50,
                        ),
                        clause_index=i,
                        research_question=(
                            "Как российское право регулирует ограничение договорной ответственности сторон и допустимо ли согласовать "
                            "предел ответственности в договоре?"
                        ),
                    )
                )
        return candidates


class TerminationDetector:
    name = "termination"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        candidates = []
        for i, clause in _clauses_of_type(clauses, ClauseType.TERMINATION):
            no_notice = _contains_any(clause.normalized_text, _NO_NOTICE_TERMINATION_MARKERS)
            has_notice_period = _contains_any(clause.normalized_text, _NOTICE_PERIOD_MARKERS)
            if no_notice and not has_notice_period:
                candidates.append(
                    RiskCandidate(
                        detector=self.name, risk_type=RiskType.ONE_SIDED_TERMINATION, category=RiskCategory.LEGAL,
                        classification=RiskClassification.UNFAVORABLE,
                        title="Расторжение без уведомления",
                        description=(
                            f"Пункт {clause.clause_number or i} допускает отказ от договора без предварительного уведомления и обоснования."
                        ),
                        why_it_matters=(
                            "Контрагент может прекратить договор внезапно, не оставляя времени на подготовку к прекращению отношений."
                        ),
                        severity_inputs=SeverityInputs(legal_impact=45, financial_impact=50, probability=40, scope=50, irreversibility=40),
                        clause_index=i,
                        research_question=(
                            "Как российское право регулирует односторонний отказ стороны от исполнения договора и какие последствия это "
                            "влечет?"
                        ),
                    )
                )
        return candidates


class PaymentRiskDetector:
    name = "payment_risk"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        candidates = []
        for i, clause in _clauses_of_type(clauses, ClauseType.PAYMENT):
            if _contains_any(clause.normalized_text, _FULL_PREPAYMENT_MARKERS):
                candidates.append(
                    RiskCandidate(
                        detector=self.name, risk_type=RiskType.PAYMENT_RISK, category=RiskCategory.FINANCIAL,
                        classification=RiskClassification.UNFAVORABLE,
                        title="Полная предоплата",
                        description=f"Пункт {clause.clause_number or i} требует 100% предоплаты до исполнения обязательств контрагентом.",
                        why_it_matters="Плательщик несет полный риск неисполнения при отсутствии встречного обеспечения.",
                        severity_inputs=SeverityInputs(legal_impact=20, financial_impact=70, probability=30, scope=40, irreversibility=50),
                        clause_index=i,
                    )
                )
        return candidates


class IPRiskDetector:
    name = "ip_risk"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        if contract_type not in (ContractType.LICENSE, ContractType.SOFTWARE, ContractType.SERVICE):
            return []
        ip_clauses = _clauses_of_type(clauses, ClauseType.INTELLECTUAL_PROPERTY)
        if not ip_clauses and contract_type in (ContractType.LICENSE, ContractType.SOFTWARE):
            return [
                RiskCandidate(
                    detector=self.name, risk_type=RiskType.IP_RISK, category=RiskCategory.LEGAL,
                    classification=RiskClassification.MISSING_PROTECTION,
                    title="Не урегулированы права на интеллектуальную собственность",
                    description="Договор данного типа не содержит пункта об интеллектуальной собственности.",
                    why_it_matters=(
                        "Без явного урегулирования прав на результаты интеллектуальной деятельности возможны споры о принадлежности прав."
                    ),
                    severity_inputs=SeverityInputs(legal_impact=55, financial_impact=40, probability=35, scope=50, irreversibility=60),
                    clause_index=None,
                )
            ]
        return []


class ConfidentialityDetector:
    name = "confidentiality"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        confidentiality_clauses = _clauses_of_type(clauses, ClauseType.CONFIDENTIALITY)
        if contract_type == ContractType.NDA and not confidentiality_clauses:
            return [
                RiskCandidate(
                    detector=self.name, risk_type=RiskType.CONFIDENTIALITY_RISK, category=RiskCategory.LEGAL,
                    classification=RiskClassification.MISSING_PROTECTION,
                    title="NDA без пункта о конфиденциальности",
                    description="Документ классифицирован как NDA, но не содержит пункта о конфиденциальности.",
                    why_it_matters="Соглашение о неразглашении без определения конфиденциальной информации фактически не защищает стороны.",
                    severity_inputs=SeverityInputs(legal_impact=70, financial_impact=40, probability=40, scope=60, irreversibility=50),
                    clause_index=None,
                )
            ]
        candidates = []
        for i, clause in confidentiality_clauses:
            is_symmetric = _contains_any(clause.normalized_text, _SYMMETRIC_OBLIGATION_MARKERS)
            mentions_specific_role = _contains_any(clause.normalized_text, _SPECIFIC_ROLE_MARKERS)
            if mentions_specific_role and not is_symmetric:
                candidates.append(
                    RiskCandidate(
                        detector=self.name, risk_type=RiskType.CONFIDENTIALITY_RISK, category=RiskCategory.COMMERCIAL,
                        classification=RiskClassification.UNFAVORABLE,
                        title="Односторонняя конфиденциальность",
                        description=f"Пункт {clause.clause_number or i} может обязывать к конфиденциальности только одну сторону.",
                        why_it_matters="Односторонние обязательства о конфиденциальности не защищают вторую сторону симметрично.",
                        severity_inputs=SeverityInputs(legal_impact=25, financial_impact=20, probability=30, scope=30, irreversibility=20),
                        clause_index=i,
                    )
                )
        return candidates


class PersonalDataDetector:
    name = "personal_data"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        mentions_pd = any("персональн" in c.normalized_text.lower() for c in clauses)
        has_pd_clause = bool(_clauses_of_type(clauses, ClauseType.PERSONAL_DATA))
        if mentions_pd and not has_pd_clause:
            return [
                RiskCandidate(
                    detector=self.name, risk_type=RiskType.DATA_PROTECTION_RISK, category=RiskCategory.COMPLIANCE,
                    classification=RiskClassification.MISSING_PROTECTION,
                    title="Обработка персональных данных не урегулирована отдельным пунктом",
                    description="Договор упоминает персональные данные, но не содержит отдельного пункта об их обработке.",
                    why_it_matters=(
                        "152-ФЗ «О персональных данных» предъявляет отдельные требования к оформлению обработки персональных данных."
                    ),
                    severity_inputs=SeverityInputs(legal_impact=60, financial_impact=30, probability=30, scope=40, irreversibility=30),
                    clause_index=None,
                    research_question=(
                        "Какие требования законодательства РФ о персональных данных применяются к их обработке в рамках "
                        "гражданско-правового договора?"
                    ),
                )
            ]
        return []


class DisputeRiskDetector:
    name = "dispute_risk"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        candidates = []
        dispute_clauses = _clauses_of_type(clauses, ClauseType.DISPUTE_RESOLUTION) + _clauses_of_type(clauses, ClauseType.JURISDICTION)
        if not dispute_clauses and contract_type != ContractType.NDA:
            candidates.append(
                RiskCandidate(
                    detector=self.name, risk_type=RiskType.DISPUTE_RISK, category=RiskCategory.PROCEDURAL,
                    classification=RiskClassification.MISSING_PROTECTION,
                    title="Не определен порядок разрешения споров",
                    description="Договор не содержит пункта о порядке разрешения споров или подсудности.",
                    why_it_matters=(
                        "При отсутствии договоренности применяются общие правила подсудности, что может быть неудобно одной из сторон."
                    ),
                    severity_inputs=SeverityInputs(legal_impact=30, financial_impact=25, probability=25, scope=30, irreversibility=20),
                    clause_index=None,
                )
            )
        for i, clause in dispute_clauses:
            if _contains_any(clause.normalized_text, _FOREIGN_JURISDICTION_MARKERS):
                candidates.append(
                    RiskCandidate(
                        detector=self.name, risk_type=RiskType.JURISDICTION_RISK, category=RiskCategory.PROCEDURAL,
                        classification=RiskClassification.UNFAVORABLE,
                        title="Иностранная юрисдикция/арбитраж",
                        description=f"Пункт {clause.clause_number or i} предусматривает разрешение споров в иностранной юрисдикции.",
                        why_it_matters="Судебная защита за рубежом обычно существенно дороже и медленнее для российской стороны.",
                        severity_inputs=SeverityInputs(legal_impact=35, financial_impact=60, probability=20, scope=40, irreversibility=30),
                        clause_index=i,
                    )
                )
        return candidates


class PenaltyDetector:
    name = "penalty"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        candidates = []
        for i, clause in _clauses_of_type(clauses, ClauseType.PENALTY):
            mentions_customer_penalty = any(
                kw in clause.normalized_text
                for kw in ("Заказчик уплачивает", "Заказчик выплачивает", "Покупатель уплачивает", "Покупатель выплачивает")
            )
            mentions_supplier_penalty = any(
                kw in clause.normalized_text
                for kw in ("Исполнитель уплачивает", "Поставщик уплачивает", "Исполнитель выплачивает", "Поставщик выплачивает")
            )
            if mentions_customer_penalty and not mentions_supplier_penalty:
                candidates.append(
                    RiskCandidate(
                        detector=self.name, risk_type=RiskType.PENALTY_RISK, category=RiskCategory.FINANCIAL,
                        classification=RiskClassification.UNFAVORABLE,
                        title="Односторонняя неустойка",
                        description=f"Пункт {clause.clause_number or i} устанавливает неустойку только для одной стороны.",
                        why_it_matters="Асимметричная неустойка создает финансовый риск преимущественно для одной стороны договора.",
                        severity_inputs=SeverityInputs(legal_impact=30, financial_impact=55, probability=35, scope=30, irreversibility=30),
                        clause_index=i,
                    )
                )
        return candidates


class IndemnityDetector:
    name = "indemnity"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        candidates = []
        for i, clause in enumerate(clauses):
            if clause.clause_type in (ClauseType.INDEMNITY, ClauseType.LIABILITY) and _contains_any(clause.normalized_text,
                _BROAD_INDEMNITY_MARKERS):
                candidates.append(
                    RiskCandidate(
                        detector=self.name, risk_type=RiskType.PENALTY_RISK, category=RiskCategory.FINANCIAL,
                        classification=RiskClassification.HIGH_RISK,
                        title="Расширенное возмещение убытков",
                        description=(
                            f"Пункт {clause.clause_number or i} предусматривает возмещение убытков в широком объеме, включая "
                            f"косвенные/упущенную выгоду."
                        ),
                        why_it_matters=(
                            "Возмещение косвенных убытков и упущенной выгоды обычно существенно увеличивает потенциальный размер "
                            "ответственности."
                        ),
                        severity_inputs=SeverityInputs(legal_impact=45, financial_impact=75, probability=25, scope=50, irreversibility=45),
                        clause_index=i,
                    )
                )
        return candidates


class ChangeControlDetector:
    name = "change_of_control"

    def detect(self, clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
        if contract_type not in (ContractType.SERVICE, ContractType.SUPPLY, ContractType.LICENSE, ContractType.LEASE):
            return []
        if not _clauses_of_type(clauses, ClauseType.CHANGE_OF_CONTROL):
            return [
                RiskCandidate(
                    detector=self.name, risk_type=RiskType.CHANGE_OF_CONTROL_RISK, category=RiskCategory.OPERATIONAL,
                    classification=RiskClassification.MISSING_PROTECTION,
                    title="Не урегулирована смена контроля",
                    description="Договор не содержит пункта о последствиях смены контроля над одной из сторон.",
                    why_it_matters="Без такого пункта смена собственника контрагента не дает права на пересмотр или расторжение договора.",
                    severity_inputs=SeverityInputs(legal_impact=20, financial_impact=25, probability=15, scope=30, irreversibility=20),
                    clause_index=None,
                )
            ]
        return []


ALL_DETECTORS: list[RiskDetector] = [
    MissingClauseDetector(), AmbiguityDetector(), LiabilityDetector(), TerminationDetector(),
    PaymentRiskDetector(), IPRiskDetector(), ConfidentialityDetector(), PersonalDataDetector(),
    DisputeRiskDetector(), PenaltyDetector(), IndemnityDetector(), ChangeControlDetector(),
]


def run_all_detectors(clauses: list[ExtractedClause], contract_type: ContractType) -> list[RiskCandidate]:
    candidates: list[RiskCandidate] = []
    for detector in ALL_DETECTORS:
        candidates.extend(detector.detect(clauses, contract_type))
    return candidates
