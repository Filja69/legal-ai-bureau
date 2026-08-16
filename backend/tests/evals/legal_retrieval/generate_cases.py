"""Phase 5 retrieval benchmark dataset (brief §30-31, §37-38). Extends the
Phase 2 hand-written case_001-006 with 50 additional deterministic cases
across 8 categories: exact article, semantic paraphrase, multi-concept,
temporal, court practice, conflicting practice, contract-risk, adversarial.

Every query is written against the actual mock dataset content
(app/sources/mock/dataset.py) — expected_articles/case_numbers are what the
mock text and dates genuinely support, never guessed. Per brief §34 this
dataset is not to be edited to make a later benchmark run look better; if a
case turns out to be wrong, fix it with a documented reason, don't delete it.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent
CASES: list[dict] = []


def add(case_id: str, category: str, query: str, **kwargs) -> None:
    case = {"case_id": case_id, "category": category, "query": query, "mode": "hybrid", "top_k": kwargs.pop("top_k",
        5), "effective_at": None}
    case.update(kwargs)
    CASES.append(case)


# --- 10 exact article (literal citation-shaped queries) ---
add("case_007", "exact_article", "статья 309 ГК РФ надлежащее исполнение обязательств", expected_articles=["309"])
add("case_008", "exact_article", "статья 310 ГК РФ односторонний отказ от исполнения обязательства", expected_articles=["310"])
add("case_009", "exact_article", "статья 314 ГК РФ срок исполнения обязательства", expected_articles=["314"])
add("case_010", "exact_article", "статья 393 ГК РФ возмещение убытков должником", expected_articles=["393"])
add("case_011", "exact_article", "статья 401 ГК РФ ответственность за неисполнение обязательства", expected_articles=["401"])
add("case_012", "exact_article", "статья 6 152-ФЗ законная и справедливая основа обработки персональных данных", expected_articles=["6"])
add("case_013", "exact_article", "статья 9 152-ФЗ согласие субъекта персональных данных", expected_articles=["9"])
add("case_014", "exact_article", "статья 333 ГК РФ уменьшение неустойки судом", expected_articles=["333"])
add("case_015", "exact_article", "статья 309 ГК РФ в редакции 2024 года", effective_at="2024-06-01", expected_articles=["309"],
    expected_effective_to="2025-01-01")
add("case_016", "exact_article", "статья 310 ГК РФ в редакции до 2023 года", effective_at="2022-01-01", expected_articles=["310"],
    expected_effective_to="2023-06-01")

# --- 10 semantic paraphrase (no article number, natural-language phrasing) ---
add("case_017", "semantic_paraphrase",
    "Должны ли обязательства исполняться в точном соответствии с условиями договора и требованиями закона?", expected_articles=["309"])
add("case_018", "semantic_paraphrase", "Вправе ли сторона в любой момент прекратить исполнение обязательства по своей воле?",
    expected_articles=["310"])
add("case_019", "semantic_paraphrase", "Когда наступает срок исполнения, если договор определяет лишь период, а не точный день?",
    expected_articles=["314"])
add("case_020", "semantic_paraphrase", "Обязан ли должник компенсировать кредитору причиненные нарушением убытки?",
    expected_articles=["393"])
add("case_021", "semantic_paraphrase", "При каких условиях лицо несет ответственность за неисполнение обязательства — нужна ли вина?",
    expected_articles=["401"])
add("case_022", "semantic_paraphrase", "На какой основе должна происходить обработка персональных данных гражданина?",
    expected_articles=["6"])
add("case_023", "semantic_paraphrase", "Нужно ли свободное и добровольное согласие человека на обработку его персональных данных?",
    expected_articles=["9"])
add("case_024", "semantic_paraphrase", "Может ли суд снизить размер неустойки, если она явно несоразмерна последствиям нарушения?",
    expected_articles=["333"])
add("case_025", "semantic_paraphrase",
    "Допустим ли отказ от исполнения договора в одностороннем порядке вне предусмотренных законом случаев?", expected_articles=["310"])
add("case_026", "semantic_paraphrase", "Каким стандартом должно отвечать исполнение договорных обязательств сторонами?",
    expected_articles=["309"])

# --- 10 multi-concept (two related legal concepts in one query) ---
add(
    "case_027", "multi_concept", "ответственность должника и возмещение убытков при ненадлежащем исполнении обязательства",
    expected_articles=["401", "393"], top_k=8,
)
add("case_028", "multi_concept", "надлежащее исполнение обязательства и односторонний отказ от договора", expected_articles=["309",
    "310"], top_k=8)
add("case_029", "multi_concept", "обработка персональных данных и согласие субъекта на такую обработку", expected_articles=["6",
    "9"], top_k=8)
add("case_030", "multi_concept", "срок исполнения обязательства и ответственность за его нарушение", expected_articles=["314",
    "401"], top_k=8)
add("case_031", "multi_concept", "убытки кредитора и вина должника как условие ответственности", expected_articles=["393", "401"], top_k=8)
add("case_032", "multi_concept", "неустойка за нарушение обязательства и её уменьшение судом", expected_articles=["333"], top_k=8)
add("case_033", "multi_concept", "неустойка и убытки как последствия нарушения обязательства", expected_articles=["333", "393"], top_k=8)
add(
    "case_034", "multi_concept", "законность обработки персональных данных и надлежащее исполнение обязательств оператором",
    expected_articles=["6", "309"], top_k=8,
)
add(
    "case_035", "multi_concept", "односторонний отказ от исполнения и ответственность за неисполнение обязательства",
    expected_articles=["310", "401"], top_k=8,
)
add("case_036", "multi_concept", "возмещение убытков и уменьшение неустойки судом при явной несоразмерности", expected_articles=["393",
    "333"], top_k=8)

# --- 5 temporal (effective_at must select the legally correct redaction) ---
add("case_037", "temporal", "надлежащим образом", effective_at="2024-06-01", expected_articles=["309"], expected_effective_to="2025-01-01",
    top_k=3)
add("case_038", "temporal", "надлежащим образом", effective_at="2025-06-01", expected_articles=["309"], expected_effective_to=None, top_k=3)
add("case_039", "temporal", "односторонний отказ от исполнения обязательства", effective_at="2022-01-01", expected_articles=["310"],
    expected_effective_to="2023-06-01", top_k=3)
add("case_040", "temporal", "односторонний отказ от исполнения обязательства", effective_at="2024-01-01", expected_articles=["310"],
    expected_effective_to=None, top_k=3)
add("case_041", "temporal", "обычаями делового оборота исполнение обязательства", effective_at="2025-06-01", expected_articles=["309"],
    expected_effective_to=None, top_k=3)

# --- 5 court practice (surface a specific real mock decision) ---
add("case_042", "court_practice", "взыскание задолженности по договору оказания услуг ненадлежащее исполнение",
    expected_case_numbers=["А40-000001/2025"], top_k=5)
add("case_043", "court_practice", "односторонний отказ от исполнения договора поставки правомерность",
    expected_case_numbers=["А40-000002/2025"], top_k=5)
add("case_044", "court_practice", "апелляционная жалоба на решение по взысканию задолженности", expected_case_numbers=["09АП-000003/2025"],
    top_k=5)
add("case_045", "court_practice", "снижение неустойки судом за просрочку оплаты по договору поставки",
    expected_case_numbers=["А40-000004/2025"], top_k=5)
add("case_046", "court_practice", "отказ в снижении неустойки недоказанность несоразмерности", expected_case_numbers=["А40-000005/2025"],
    top_k=5)

# --- 5 conflicting practice (both sides of the ст.333 split must surface together) ---
add(
    "case_047", "conflicting_practice", "применение статьи 333 ГК РФ к неустойке за просрочку оплаты по договору поставки",
    expected_case_numbers=["А40-000004/2025", "А40-000005/2025"], top_k=10,
)
add("case_048", "conflicting_practice", "снижение неустойки судом по договору поставки", expected_case_numbers=["А40-000004/2025"],
    top_k=10)
add("case_049", "conflicting_practice", "отказ снижать неустойку по договору поставки при недоказанной несоразмерности",
    expected_case_numbers=["А40-000005/2025"], top_k=10)
add(
    "case_050", "conflicting_practice", "противоречивая практика применения статьи 333 ГК РФ к неустойке по договорам поставки",
    expected_case_numbers=["А40-000004/2025", "А40-000005/2025"], top_k=10,
)
add("case_051", "conflicting_practice", "явная несоразмерность неустойки последствиям нарушения обязательства статья 333",
    expected_articles=["333"], expected_case_numbers=["А40-000004/2025"], top_k=10)

# --- 5 contract-risk (queries mirroring Phase 4 risk_verification research_questions) ---
add(
    "case_052", "contract_risk", "ограничение договорной ответственности сторон надлежащее исполнение обязательства",
    expected_articles=["309", "401"], top_k=8,
)
add(
    "case_053", "contract_risk",
    "какие требования законодательства РФ о персональных данных применяются к их обработке в рамках гражданско-правового договора",
    expected_articles=["6", "9"], top_k=8,
)
add("case_054", "contract_risk", "правомерность одностороннего отказа стороны от исполнения договора", expected_articles=["310"], top_k=8)
add("case_055", "contract_risk", "несоразмерность договорной неустойки последствиям нарушения обязательства", expected_articles=["333"],
    top_k=8)
add("case_056", "contract_risk", "возмещение убытков контрагенту при неисполнении договорного обязательства", expected_articles=["393"],
    top_k=8)

# --- 5 adversarial (fabricated citations must resolve BROKEN/UNVERIFIED, never
# VERIFIED/MOCK — the citation-validation path, not raw retrieval, is what's
# actually asked to defend against hallucination here: a fabricated article
# number can never be *retrieved* since nothing is indexed under it, so the
# meaningful test is whether CitationValidator confirms it anyway) ---
add("case_057", "adversarial", "статья 999 ГК РФ об ответственности за нарушение цифровых обязательств", citation_text="ГК РФ, статья 999",
    expected_citation_status="unverified")
add("case_058", "adversarial", "статья 1500 ГК РФ регулирование цифровых финансовых активов", citation_text="ГК РФ, статья 1500",
    expected_citation_status="unverified")
add("case_059", "adversarial", "309-ФЗ статья 12 об исполнении обязательств", citation_text="309-ФЗ, статья 12",
    expected_citation_status="unverified")
add("case_060", "adversarial", "статья 500 ГК РФ об электронных обязательствах", citation_text="ГК РФ, статья 500",
    expected_citation_status="unverified")
add("case_061", "adversarial", "статья 314 ГК РФ", citation_text="ГК РФ, статья 999", expected_citation_status="unverified")

for case in CASES:
    (OUT / f"{case['case_id']}.json").write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"Generated {len(CASES)} retrieval eval cases into {OUT}")
