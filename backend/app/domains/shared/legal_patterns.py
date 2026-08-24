"""Deterministic regex patterns for extracting structured facts (dates,
amounts, party names/roles) from Russian-language legal document text.

Originally written for Document analysis (Phase 9.2, `app/domains/documents/
analysis.py`); promoted here in Phase 9.3 so the Litigation domain's fact
extractor (`app/domains/litigation/fact_extractor.py`) reuses the exact same
patterns instead of a second, potentially-drifting copy — "do not create a
second research engine" (brief §18) applies equally to not creating a second
regex library.

Known limitation, unchanged from Phase 9.2: these patterns are Russian-legal-
document-specific (`руб`, `ООО`, `Заказчик`, etc.) and will not match
English-language contract text (e.g. "150000 RUB", "Contractor:") — this was
observed live in `docs/PHASE-9-2-INTEGRATION-VERIFICATION.md` §8, not fixed
here, since the project's stated jurisdiction scope is RU (LEGAL-PRD.md §3).
"""
from __future__ import annotations

import re

DATE_NUMERIC = re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")
DATE_WORDY = re.compile(
    r"\b\d{1,2}\s+(?:январ[а-я]+|феврал[а-я]+|март[а-я]*|апрел[а-я]+|ма[йя]|июн[а-я]+|июл[а-я]+"
    r"|август[а-я]*|сентябр[а-я]+|октябр[а-я]+|ноябр[а-я]+|декабр[а-я]+)\s+\d{4}\s*г?\.?",
    re.IGNORECASE,
)
# Thousands-separator class: regular space, non-breaking space (U+00A0) and
# narrow no-break space (U+202F) — Word-authored Russian documents routinely
# group digits with a non-breaking space specifically so the number can't be
# split across a line break, e.g. "30 000 000 рублей". Previously
# this class was `[  ]` (two ASCII spaces, effectively just one) — real text
# mixing a non-breaking separator with a later regular-space separator (as
# happens whenever a page/paragraph break normalizes only some of them) would
# silently match starting from the LAST unbroken group instead of the whole
# number, e.g. matching just "000 000" (=> parsed as 0) out of "30 000 000".
#
# The optional (?:\([^)]{0,40}\)\s*)? bridges a parenthetical amount-in-words
# spellout between the digits and the currency word — a standard Russian
# legal-document convention ("5000000 (пять миллионов) рублей") that would
# otherwise never match, since \s* alone can't span the parenthetical. Bounded
# to 40 chars so an unrelated parenthetical elsewhere in the sentence can't be
# swept in.
AMOUNT = re.compile(
    r"\b\d+(?:[   ]\d{3})*(?:[.,]\d{2})?\s*(?:\([^)]{0,40}\)\s*)?(?:руб(?:лей|ля)?|₽|USD|\$|EUR|€)\b",
    re.IGNORECASE,
)
PARTY_ENTITY = re.compile(r'(?:ООО|АО|ПАО|ЗАО|ИП)\s*[«"]([^»"]+)[»"]')
PARTY_ROLE = re.compile(
    r"^(Заказчик|Исполнитель|Продавец|Покупатель|Арендодатель|Арендатор|Поставщик|Подрядчик)\s*[:\-—]\s*(.+)$",
    re.MULTILINE,
)
