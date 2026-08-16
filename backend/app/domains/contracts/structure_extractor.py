"""ContractStructureExtractor — brief §7, §10-11.

Segmentation and clause numbering/position are fully deterministic (regex
over paragraph boundaries) — never LLM-guessed, so redline/citation
provenance (brief §11-12) always points at real, reproducible offsets into
`original_text`. Clause *classification* (which ClauseType a clause is) is
also deterministic here — a keyword-taxonomy match, not an LLM call —
because that's both more reliable than depending on `LLM_PROVIDER=mock` and
keeps the pipeline honestly functional without a live model key. An LLM
refinement hook is defined but not required (see `LegalGateway`-based
override).
"""
from __future__ import annotations

import re

from app.models.contracts import ClauseType

_CLAUSE_PATTERN = re.compile(r"^(?P<number>\d+(?:\.\d+)*)\.?\s+(?P<rest>.+)", re.DOTALL)

# Keyword taxonomy — Russian legal-drafting vocabulary per ClauseType. Order
# matters only in that a clause is assigned the type with the most keyword
# hits; ties broken by taxonomy order (earlier wins), a deterministic rule.
_CLAUSE_KEYWORDS: dict[ClauseType, list[str]] = {
    ClauseType.DEFINITIONS: ["термин", "понятия, используемые", "для целей настоящего договора"],
    ClauseType.CONFIDENTIALITY: ["конфиденциальн", "неразглашени"],
    ClauseType.PENALTY: ["неустойк", "штраф", "пеня", "пени"],
    ClauseType.SUBJECT: ["предмет договора"],
    ClauseType.PRICE: ["цена договора", "стоимость услуг", "стоимость товара"],
    ClauseType.PAYMENT: ["оплат", "платеж", "порядок расчетов", "предоплат", "постоплат"],
    ClauseType.DELIVERY: ["поставка", "доставка", "передача товара", "срок поставки"],
    ClauseType.ACCEPTANCE: ["приемка", "акт сдачи-приемки", "подписание акта"],
    ClauseType.WARRANTY: ["гарантия", "гарантийный срок", "гарантирует"],
    ClauseType.LIABILITY: ["ответственность", "убытки"],
    ClauseType.INDEMNITY: ["возмещение вреда", "освобождает от ответственности", "indemnif"],
    ClauseType.FORCE_MAJEURE: ["форс-мажор", "обстоятельства непреодолимой силы"],
    ClauseType.TERM: ["срок действия договора", "вступает в силу", "действует до"],
    ClauseType.RENEWAL: ["автоматически продлевается", "пролонгация", "продление срока"],
    ClauseType.TERMINATION: [
        "расторжение", "отказ от договора", "прекращение договора",
        "отказаться от исполнения", "односторонний отказ",
    ],
    ClauseType.PERSONAL_DATA: ["персональных данных", "обработка персональных"],
    ClauseType.INTELLECTUAL_PROPERTY: ["интеллектуальной собственности", "исключительное право", "авторские права"],
    ClauseType.LICENSE: ["лицензия", "лицензионное вознаграждение", "право использования"],
    ClauseType.NON_COMPETE: ["не конкурировать", "неконкуренции"],
    ClauseType.NON_SOLICIT: ["переманивание", "не привлекать сотрудников"],
    ClauseType.DISPUTE_RESOLUTION: ["споры", "претензионный порядок", "разрешение споров"],
    ClauseType.JURISDICTION: ["подсудность", "арбитражный суд города"],
    ClauseType.GOVERNING_LAW: ["применимое право", "законодательством российской федерации"],
    ClauseType.AUDIT: ["право на аудит", "проверку деятельности"],
    ClauseType.INSURANCE: ["страхование", "страховой полис"],
    ClauseType.ASSIGNMENT: ["уступка права требования", "передача прав по договору"],
    ClauseType.CHANGE_OF_CONTROL: ["смена контроля", "изменение состава участников"],
    ClauseType.NOTICE: ["уведомление", "письменное извещение"],
}


def normalize_text(text: str) -> str:
    """Whitespace/encoding cleanup only — never a paraphrase (brief §11)."""
    return " ".join(text.split())


def classify_clause(normalized_text: str) -> tuple[ClauseType, float]:
    text_lower = normalized_text.lower()
    best_type = ClauseType.OTHER
    best_hits = 0
    for clause_type, keywords in _CLAUSE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits > best_hits:
            best_hits = hits
            best_type = clause_type
    confidence = min(1.0, 0.5 + 0.25 * best_hits) if best_hits else 0.2
    return best_type, confidence


class ExtractedClause:
    def __init__(
        self, clause_number: str | None, original_text: str, normalized_text: str,
        clause_type: ClauseType, confidence: float, position_start: int, position_end: int,
    ) -> None:
        self.clause_number = clause_number
        self.original_text = original_text
        self.normalized_text = normalized_text
        self.clause_type = clause_type
        self.confidence = confidence
        self.position_start = position_start
        self.position_end = position_end


class ContractStructureExtractor:
    def extract(self, raw_text: str) -> list[ExtractedClause]:
        clauses: list[ExtractedClause] = []
        cursor = 0
        for paragraph in raw_text.split("\n\n"):
            stripped = paragraph.strip()
            start = raw_text.index(paragraph, cursor) if paragraph else cursor
            end = start + len(paragraph)
            cursor = end

            if not stripped:
                continue

            match = _CLAUSE_PATTERN.match(stripped)
            clause_number = match.group("number") if match else None
            body = match.group("rest") if match else stripped

            normalized = normalize_text(body)
            if not normalized:
                continue

            clause_type, confidence = classify_clause(normalized)
            clauses.append(
                ExtractedClause(
                    clause_number=clause_number,
                    original_text=stripped,
                    normalized_text=normalized,
                    clause_type=clause_type,
                    confidence=confidence,
                    position_start=start,
                    position_end=end,
                )
            )
        return clauses
