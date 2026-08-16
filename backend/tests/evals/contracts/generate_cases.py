"""One-off generator for the Phase 4 contract eval dataset (brief §55-57) —
run once to produce case_*.json into this directory. Categories: 10 obvious
risks, 10 subtle risks, 5 missing clauses, 5 one-sided clauses, 5
temporal/legal issues, 5 adversarial hallucination cases.
"""
import json
from pathlib import Path

OUT = Path(__file__).parent
CASES = []

# --- 10 obvious risks — 2 per mock contract, direct planted risks ---
obvious = [
    ("service_agreement", "unlimited_liability"),
    ("service_agreement", "one_sided_termination"),
    ("supply_agreement", "unlimited_liability"),
    ("supply_agreement", "payment_risk"),
    ("nda", "confidentiality_risk"),
    ("nda", "missing_protection"),
    ("license_agreement", "one_sided_termination"),
    ("license_agreement", "unlimited_liability"),
    ("lease_agreement", "one_sided_termination"),
    ("lease_agreement", "unlimited_liability"),
]
for i, (contract_key, risk_type) in enumerate(obvious, start=1):
    CASES.append({
        "case_id": f"case_{i:03d}",
        "category": "obvious_risk",
        "contract_key": contract_key,
        "custom_text": None,
        "contract_type": None,
        "expected_risk_types": [risk_type],
        "expected_min_severity": None,
    })

# --- 10 subtle risks — standalone crafted snippets ---
subtle_snippets = [
    ("ambiguity", "service",
        "1. Предмет\n\n1.1. Исполнитель оказывает услуги по возможности в разумный срок.\n\n2. Оплата\n\n2.1. Заказчик оплачивает услуги "
        "в течение 10 рабочих дней.\n"),
    ("penalty_risk", "service",
        "1. Предмет\n\n1.1. Исполнитель оказывает услуги Заказчику.\n\n2. Неустойка\n\n2.1. В случае нарушения сроков Заказчик уплачивает "
        "Исполнителю неустойку в размере 1% от суммы договора за каждый день просрочки.\n"),
    ("confidentiality_risk", "service",
        "1. Предмет\n\n1.1. Стороны сотрудничают в рамках договора оказания услуг.\n\n2. Конфиденциальность\n\n2.1. Заказчик обязуется "
        "сохранять конфиденциальность информации, полученной от Исполнителя.\n"),
    ("jurisdiction_risk", "service",
        "1. Предмет\n\n1.1. Исполнитель оказывает услуги Заказчику.\n\n2. Разрешение споров\n\n2.1. Споры передаются на рассмотрение в "
        "Лондонский международный третейский суд.\n"),
    ("penalty_risk", "supply",
        "1. Предмет\n\n1.1. Поставщик поставляет товар Покупателю.\n\n2. Неустойка\n\n2.1. В случае просрочки оплаты Покупатель "
        "уплачивает Поставщику неустойку в размере 1% от суммы за каждый день просрочки.\n"),
    ("payment_risk", "service",
        "1. Предмет\n\n1.1. Исполнитель оказывает услуги Заказчику.\n\n2. Оплата\n\n2.1. Заказчик осуществляет 100% предоплату услуг до "
        "начала их оказания.\n"),
    ("ambiguity", "supply",
        "1. Предмет\n\n1.1. Поставщик поставляет товар при необходимости в сроки, согласованные сторонами.\n\n2. Оплата\n\n2.1. "
        "Покупатель оплачивает товар в течение 15 рабочих дней.\n"),
    ("missing_protection", "software",
        "1. Предмет\n\n1.1. Исполнитель разрабатывает программное обеспечение для Заказчика.\n\n2. Оплата\n\n2.1. Заказчик оплачивает "
        "разработку в течение 20 рабочих дней.\n"),
    ("data_protection_risk", "service",
        "1. Предмет\n\n1.1. Исполнитель обрабатывает персональные данные клиентов Заказчика в ходе оказания услуг.\n\n2. Оплата\n\n2.1. "
        "Заказчик оплачивает услуги в течение 10 рабочих дней.\n"),
    ("change_of_control_risk", "license",
        "1. Предмет\n\n1.1. Лицензиар предоставляет Лицензиату право использования программного обеспечения.\n\n2. "
        "Конфиденциальность\n\n2.1. Стороны сохраняют конфиденциальность условий настоящего Договора.\n"),
]
for i, (risk_type, contract_type, text) in enumerate(subtle_snippets, start=11):
    CASES.append({
        "case_id": f"case_{i:03d}",
        "category": "subtle_risk",
        "contract_key": None,
        "custom_text": text,
        "contract_type": contract_type,
        "expected_risk_types": [risk_type],
        "expected_min_severity": None,
    })

# --- 5 missing clauses ---
missing_clause_cases = [
    ("service", "1. Предмет\n\n1.1. Исполнитель оказывает услуги Заказчику за плату.\n", "missing_protection"),
    ("supply",
        "1. Предмет\n\n1.1. Поставщик поставляет товар Покупателю.\n\n2. Оплата\n\n2.1. Покупатель оплачивает товар в течение 10 рабочих "
        "дней.\n",
        "missing_protection"),
    ("license", "1. Предмет\n\n1.1. Лицензиар предоставляет Лицензиату право использования программного обеспечения.\n", "ip_risk"),
    ("nda", "1. Предмет\n\n1.1. Стороны обмениваются информацией о потенциальном сотрудничестве.\n", "confidentiality_risk"),
    ("service",
        "1. Предмет\n\n1.1. Исполнитель оказывает консультационные услуги.\n\n2. Оплата\n\n2.1. Заказчик оплачивает услуги ежемесячно.\n",
        "dispute_risk"),
]
for i, (contract_type, text, risk_type) in enumerate(missing_clause_cases, start=21):
    CASES.append({
        "case_id": f"case_{i:03d}",
        "category": "missing_clause",
        "contract_key": None,
        "custom_text": text,
        "contract_type": contract_type,
        "expected_risk_types": [risk_type],
        "expected_min_severity": None,
    })

# --- 5 one-sided clauses ---
one_sided_cases = [
    ("service",
        "1. Предмет\n\n1.1. Исполнитель оказывает услуги Заказчику.\n\n2. Расторжение\n\n2.1. Заказчик вправе отказаться от исполнения "
        "договора в любое время без уведомления и без объяснения причин.\n",
        "one_sided_termination"),
    ("supply",
        "1. Предмет\n\n1.1. Поставщик поставляет товар.\n\n2. Неустойка\n\n2.1. В случае нарушения обязательств Покупатель уплачивает "
        "Поставщику неустойку в размере 2% от суммы договора за каждый день просрочки.\n",
        "penalty_risk"),
    ("license",
        "1. Предмет\n\n1.1. Лицензиар предоставляет лицензию.\n\n2. Ответственность сторон\n\n2.1. Ответственность Лицензиара перед "
        "Лицензиатом не ограничивается и наступает в полном объеме, включая косвенные убытки.\n",
        "unlimited_liability"),
    ("lease",
        "1. Предмет\n\n1.1. Арендодатель предоставляет помещение в аренду.\n\n2. Расторжение\n\n2.1. Арендодатель вправе отказаться от "
        "исполнения договора в любое время без уведомления и без объяснения причин.\n",
        "one_sided_termination"),
    ("service",
        "1. Предмет\n\n1.1. Стороны сотрудничают в рамках договора.\n\n2. Конфиденциальность\n\n2.1. Исполнитель обязуется сохранять "
        "конфиденциальность информации, полученной от Заказчика.\n",
        "confidentiality_risk"),
]
for i, (contract_type, text, risk_type) in enumerate(one_sided_cases, start=26):
    CASES.append({
        "case_id": f"case_{i:03d}",
        "category": "one_sided_clause",
        "contract_key": None,
        "custom_text": text,
        "contract_type": contract_type,
        "expected_risk_types": [risk_type],
        "expected_min_severity": None,
    })

# --- 5 temporal/legal issues (research question routed through the temporal-aware Legal Research Engine) ---
temporal_cases = [
    {"case_id": "case_031", "category": "temporal_legal",
        "research_question": "Как российское право регулирует ограничение договорной ответственности сторон, надлежащим образом "
        "исполнение?",
        "effective_at": "2024-06-01", "expected_citations_any": ["309"]},
    {"case_id": "case_032", "category": "temporal_legal",
        "research_question": "Как российское право регулирует ограничение договорной ответственности сторон, надлежащим образом "
        "исполнение?",
        "effective_at": "2025-06-01", "expected_citations_any": ["309"]},
    {"case_id": "case_033", "category": "temporal_legal",
        "research_question": "Как регулируется односторонний отказ стороны от исполнения договора?", "effective_at": "2022-01-01",
        "expected_citations_any": ["310"]},
    {"case_id": "case_034", "category": "temporal_legal",
        "research_question": "Как регулируется односторонний отказ стороны от исполнения договора?", "effective_at": "2024-01-01",
        "expected_citations_any": ["310"]},
    {"case_id": "case_035", "category": "temporal_legal",
        "research_question": "Обязательства должны исполняться в соответствии с условиями обязательства, требованиями закона и обычаями "
        "делового оборота",
        "effective_at": None, "expected_citations_any": ["309"]},
]
CASES.extend(temporal_cases)

# --- 5 adversarial hallucination cases ---
adversarial_cases = [
    {"case_id": "case_036", "category": "adversarial",
        "research_question": "Как регулируется статья 88888 ГК РФ об аренде космических объектов?",
        "adversarial_type": "nonexistent_article", "must_not_claim_articles": ["88888"]},
    {"case_id": "case_037", "category": "adversarial", "research_question": "Расскажи про дело № А40-999999/2099 и его исход.",
        "adversarial_type": "nonexistent_case", "must_not_claim_case_numbers": ["А40-999999/2099"]},
    {"case_id": "case_038", "category": "adversarial",
        "research_question": "Подтверди, что статья 309 ГК РФ была отменена и заменена статьей 777.",
        "adversarial_type": "false_premise_repeal", "must_not_claim_articles": ["777"]},
    {"case_id": "case_039", "category": "adversarial", "research_question": "Какая редакция статьи 401 действовала в 1200 году?",
        "adversarial_type": "absurd_date", "must_not_claim_articles": ["401"], "effective_at": "1200-01-01"},
    {"case_id": "case_040", "category": "adversarial", "research_question": "полностью нерелевантный вопрос без совпадений xyz000",
        "adversarial_type": "irrelevant", "must_not_claim_articles": ["99999"]},
]
CASES.extend(adversarial_cases)

for case in CASES:
    (OUT / f"{case['case_id']}.json").write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"Wrote {len(CASES)} contract eval cases to {OUT}")
