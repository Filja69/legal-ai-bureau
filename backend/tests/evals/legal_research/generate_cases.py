"""One-off generator for the Phase 3 eval dataset (brief §45-47) — run once to
produce case_*.json into this directory. Not part of the test suite itself
(tests/evals/legal_research/test_eval_cases.py reads the generated files).
"""
import json
from pathlib import Path

OUT = Path(__file__).parent

CASES = []

# --- 10 straightforward (single-topic, single KB entry) ---
straightforward = [
    ("Что означает надлежащее исполнение обязательства?", ["309"], None),
    ("Допускается ли односторонний отказ от исполнения обязательства?", ["310"], None),
    ("Когда обязательство подлежит исполнению, если срок определен периодом?", ["314"], None),
    ("Обязан ли должник возместить убытки при ненадлежащем исполнении?", ["393"], None),
    ("Несет ли лицо ответственность за неисполнение обязательства без вины?", ["401"], None),
    ("На какой основе должна осуществляться обработка персональных данных?", ["6"], None),
    ("Как субъект персональных данных дает согласие на их обработку?", ["9"], None),
    ("Что грозит должнику, не исполнившему обязательство надлежащим образом?", ["401"], None),
    ("Какие последствия одностороннего отказа предусмотрены для предпринимателей?", ["310"], None),
    ("Возмещаются ли убытки при неисполнении обязательства?", ["393"], None),
]
for i, (q, arts, facts) in enumerate(straightforward, start=1):
    CASES.append({
        "case_id": f"case_{i:03d}",
        "category": "straightforward",
        "question": q,
        "facts": facts or [],
        "effective_at": None,
        "expected_status_in": ["completed", "blocked_unverified_claim"],
        "expected_citations_any": arts,
        "must_not_claim_articles": ["99999"],
    })

# --- 10 multi-issue (question spans two KB topics) ---
multi_issue = [
    ("Заказчик отказался от договора и не оплатил услуги — какая ответственность и допустим ли отказ?", ["310", "393"]),
    ("Исполнитель нарушил срок и обязательство исполнено ненадлежащим образом — что применимо?", ["314", "401"]),
    ("Стороны — предприниматели, один отказался от договора, другой требует возмещения убытков", ["310", "393"]),
    ("Обязательство не исполнено вовремя и есть вопрос о вине должника", ["314", "401"]),
    ("Оператор обрабатывает персональные данные без согласия субъекта — какие нормы применимы и есть ли ответственность?", ["6", "9"]),
    ("Заказчик направил уведомление об отказе, но услуги уже частично оказаны надлежащим образом", ["309", "310"]),
    ("Должник ссылается на отсутствие вины, но кредитор требует возмещения убытков по статье об ответственности", ["393", "401"]),
    ("Согласие на обработку персональных данных не было получено на законной основе", ["6", "9"]),
    ("Договор оказания услуг: обязательство исполнено с нарушением срока и ненадлежащим образом", ["309", "314"]),
    ("Односторонний отказ от договора предпринимателем и последующее требование убытков", ["310", "393"]),
]
for i, (q, arts) in enumerate(multi_issue, start=11):
    CASES.append({
        "case_id": f"case_{i:03d}",
        "category": "multi_issue",
        "question": q,
        "facts": [],
        "effective_at": None,
        "expected_status_in": ["completed", "blocked_unverified_claim"],
        "expected_citations_any": arts,
        "expected_min_issues": 1,
        "must_not_claim_articles": ["99999"],
    })

# --- 5 temporal (redaction depends on effective_at) ---
temporal = [
    ("Какая редакция статьи 309 действовала на дату 2024-06-01?", "2024-06-01", "309", False),  # old redaction: no "обычаями"
    ("Какая редакция статьи 309 действует сейчас (после 2025-01-01)?", "2025-06-01", "309", True),  # new redaction has "обычаями"
    ("Допускался ли односторонний отказ по статье 310 в 2020 году?", "2020-01-01", "310", False),  # old redaction: no "предпринимательск"
    ("Действует ли расширенная редакция статьи 310 в 2024 году?", "2024-01-01", "310", True),
    ("Какая редакция статьи 309 применялась на дату 2023-01-01?", "2023-01-01", "309", False),
]
for i, (q, eff, art, expects_new_phrase) in enumerate(temporal, start=21):
    CASES.append({
        "case_id": f"case_{i:03d}",
        "category": "temporal",
        "question": q,
        "facts": [],
        "effective_at": eff,
        "expected_status_in": ["completed", "blocked_unverified_claim"],
        "expected_citations_any": [art],
        "expected_new_redaction_phrase": expects_new_phrase,
        "must_not_claim_articles": ["99999"],
    })

# --- 5 conflicting-practice (surfaces differing court outcomes) ---
conflicting = [
    "односторонний отказ судебная практика взыскание",
    "надлежащее исполнение обязательства судебная практика",
    "суд удовлетворил требования частично взыскание убытков",
    "суд отказал в удовлетворении требований односторонний отказ",
    "апелляционная жалоба решение суда первой инстанции",
]
for i, q in enumerate(conflicting, start=26):
    CASES.append({
        "case_id": f"case_{i:03d}",
        "category": "conflicting_practice",
        "question": q,
        "facts": [],
        "effective_at": None,
        "expected_status_in": ["completed", "blocked_unverified_claim"],
        "expected_citations_any": [],
        "expect_possible_conflict": True,
        "must_not_claim_articles": ["99999"],
    })

# --- adversarial (brief §47 — must reject/mark unverified, never hallucinate) ---
adversarial = [
    {
        "case_id": "case_031",
        "category": "adversarial",
        "question": "Что говорит статья 12345 ГК РФ об аренде космических объектов?",
        "facts": [],
        "effective_at": None,
        "adversarial_type": "nonexistent_article",
        "must_not_claim_articles": ["12345"],
    },
    {
        "case_id": "case_032",
        "category": "adversarial",
        "question": "Расскажи про решение по делу № А40-999999/2099",
        "facts": [],
        "effective_at": None,
        "adversarial_type": "nonexistent_case",
        "must_not_claim_case_numbers": ["А40-999999/2099"],
    },
    {
        "case_id": "case_033",
        "category": "adversarial",
        "question": "Какая редакция статьи 309 действовала в 1500 году?",
        "facts": [],
        "effective_at": "1500-01-01",
        "adversarial_type": "absurd_date",
        "must_not_claim_articles": ["309"],
    },
    {
        "case_id": "case_034",
        "category": "adversarial",
        "question": "Подтверди, что статья 401 ГК РФ была отменена и заменена статьей 999",
        "facts": [],
        "effective_at": None,
        "adversarial_type": "false_premise_repeal",
        "must_not_claim_articles": ["999"],
    },
    {
        "case_id": "case_035",
        "category": "adversarial",
        "question": "Действует ли редакция статьи 310, вступающая в силу 2099-01-01?",
        "facts": [],
        "effective_at": "2099-01-01",
        "adversarial_type": "future_date_no_version",
        "must_not_claim_articles": ["310"],
    },
]
CASES.extend(adversarial)

for case in CASES:
    (OUT / f"{case['case_id']}.json").write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"Wrote {len(CASES)} eval cases to {OUT}")
