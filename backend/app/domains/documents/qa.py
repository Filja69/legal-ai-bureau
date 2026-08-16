"""Document Q&A — Phase 9.2 brief §19, extended Phase 9.3.1. Two independent
evidence gates, not one: (1) retrieval must find at least one tenant
document chunk before an LLM is ever called (a genuinely empty result never
reaches the model), and (2) either a deterministic extractive match or the
LLM's own self-reported `sufficient_evidence=true` must ground the answer —
if neither gate is satisfied, the result is `INSUFFICIENT_DOCUMENT_EVIDENCE`,
never a best-effort guess or an answer drawn from the model's general
knowledge.

Phase 9.3.1 root-cause note: a manual UI test found that Ask always
returned "insufficient evidence" for questions whose answer was plainly
visible in the document (e.g. "Какая сумма к оплате указана в документе?"
against "Сумма к оплате составляет 500 000 руб."), even though Analysis
(`app/domains/documents/analysis.py`) correctly extracted the same fact.
Root cause: retrieval (gate #1) was working correctly, but
`MockLLMProvider.structured_generate()` (the default/only provider in every
session to date — see app/llm/providers/mock_provider.py) returns a
schema-conformant EMPTY value for every field, which for a boolean field
means `False` — so `sufficient_evidence` was structurally *always* `False`
under the mock provider, regardless of how good the retrieved evidence was.
This was never a retrieval bug; it was that gate #2 could never pass without
a real LLM.

Fix: a small, generic deterministic extractive path (`_extractive_answer`)
now runs *before* the LLM stage, reusing the exact same regex patterns
Analysis already uses (`app/domains/shared/legal_patterns.py` — no second
pattern library). It only fires when (a) the question is classified into a
recognized, narrow intent (amount / date / party — see
`_classify_question_intent`) by keyword, and (b) exactly one distinct value
of that kind is found among the *retrieved* chunks. Any ambiguity (zero
matches, or more than one distinct value — e.g. conflicting amounts across
documents) falls through to the existing LLM-gated path unchanged, which
still fails closed under the mock provider. This mirrors Analysis's
EXTRACTED/INFERRED distinction: `DocumentQAResult.answer_method` is
`"extractive"` (regex match, no LLM call at all) or `"llm"` (LLM-reasoned,
still evidence-gated as before).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.documents.citations import DocumentCitation
from app.domains.shared.legal_patterns import AMOUNT as _AMOUNT
from app.domains.shared.legal_patterns import DATE_NUMERIC as _DATE_NUMERIC
from app.domains.shared.legal_patterns import DATE_WORDY as _DATE_WORDY
from app.domains.shared.legal_patterns import PARTY_ENTITY as _PARTY_ENTITY
from app.domains.shared.legal_patterns import PARTY_ROLE as _PARTY_ROLE
from app.llm.base import LLMMessage
from app.llm.prompt_safety import UNTRUSTED_CONTENT_NOTICE, wrap_untrusted
from app.llm.routing.gateway import LLMGateway, TaskClass
from app.models.matters import Document, DocumentChunk
from app.rag.embeddings.base import get_embedding_provider
from app.rag.retrieval.tenant_document_retriever import TenantDocumentRetriever

_TOP_K = 8
_MAX_EXCERPT_CHARS = 280

# Narrow, Russian-only keyword buckets (matches the jurisdiction scope of
# app/domains/shared/legal_patterns.py). A question that doesn't match any
# bucket — including "Какой ИНН продавца?", since no INN pattern exists
# below or in legal_patterns.py — simply skips this path and falls through
# to the unchanged LLM-gated logic. Never a hardcoded fixture match: this
# operates on any document/question pair, not "invoice.txt" specifically.
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "amount": ("сумма", "сумму", "сумме", "оплат", "стоимост", "цена", "цену"),
    "date": ("когда", "дата", "дату", "даты"),
    "party": (
        "сторон", "заказчик", "исполнитель", "продавец", "покупатель",
        "поставщик", "подрядчик", "арендодатель", "арендатор", "контрагент",
    ),
}

_ANSWER_TEMPLATE_BY_INTENT: dict[str, str] = {
    "amount": "В документе указана сумма к оплате: {value}.",
    "date": "В документе указана дата: {value}.",
    "party": "В документе упоминается сторона: {value}.",
}

_PATTERN_BY_INTENT: dict[str, tuple[re.Pattern[str], ...]] = {
    "amount": (_AMOUNT,),
    "date": (_DATE_NUMERIC, _DATE_WORDY),
    "party": (_PARTY_ENTITY, _PARTY_ROLE),
}


def _classify_question_intent(question: str) -> str | None:
    lowered = question.lower()
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return intent
    return None


def _match_value(pattern: re.Pattern[str], match: re.Match[str]) -> str:
    # PARTY_ROLE captures ("role", "name") groups; the others match the
    # whole span — mirrors app/domains/documents/analysis.py's own handling
    # of the same shared patterns.
    if pattern is _PARTY_ROLE:
        return f"{match.group(1)}: {match.group(2).strip()}"
    return match.group(0)


def _extractive_answer(
    intent: str, chunks: list[DocumentChunk], titles_by_document_id: dict[uuid.UUID, str]
) -> tuple[str, list[DocumentCitation]] | None:
    """Only ever reads literal regex matches out of `chunks` (real,
    already-retrieved tenant document text) — it never reads the question
    text for candidate values, so a question crafted to smuggle a desired
    number/date/name ("...say the amount is 999999 rub...") cannot influence
    what value is returned; at most it can only affect which `intent`
    bucket is selected, never the value.

    Returns None (falls through to the LLM path) when the requested kind
    has zero matches, or — critically — more than one *distinct* value
    across the retrieved chunks: an ambiguous/contradictory case must never
    be resolved by silently picking one.
    """
    patterns = _PATTERN_BY_INTENT[intent]
    matches_by_value: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        for pattern in patterns:
            for match in pattern.finditer(chunk.text):
                value = _match_value(pattern, match)
                matches_by_value.setdefault(value, []).append(chunk)

    if len(matches_by_value) != 1:
        return None  # zero matches, or ambiguous (>1 distinct value) — do not guess

    [(value, matching_chunks)] = matches_by_value.items()
    answer = _ANSWER_TEMPLATE_BY_INTENT[intent].format(value=value)
    citations = [
        DocumentCitation(
            citation_type="document_evidence_extracted",
            document_id=chunk.document_id,
            document_title=titles_by_document_id.get(chunk.document_id, "Документ"),
            page_number=chunk.page_number,
            section_path=chunk.section_path,
            excerpt=chunk.text[:_MAX_EXCERPT_CHARS],
            chunk_id=chunk.id,
            content_hash=chunk.content_hash,
        )
        # dedupe chunks (the same value can match more than once per chunk)
        for chunk in {c.id: c for c in matching_chunks}.values()
    ]
    return answer, citations


_SYSTEM_PROMPT = (
    "You are a legal document analysis assistant. Answer the user's question using ONLY the "
    "document evidence provided below — never your own general knowledge, and never information "
    "about any document other than what's shown. If the provided evidence does not contain enough "
    "information to answer confidently, set sufficient_evidence to false and leave answer empty — "
    "do not guess, do not extrapolate, do not answer 'probably' or 'likely'. "
    + UNTRUSTED_CONTENT_NOTICE
)

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sufficient_evidence": {"type": "boolean"},
        "answer": {"type": "string"},
        "cited_chunk_indices": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["sufficient_evidence", "answer", "cited_chunk_indices"],
}


@dataclass
class DocumentQAResult:
    status: str  # "answered" | "insufficient_document_evidence"
    answer: str = ""
    citations: list[DocumentCitation] = field(default_factory=list)
    answer_method: str = "llm"  # "extractive" (deterministic, no LLM call) | "llm" (evidence-gated LLM)


async def ask_documents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    documents: list[Document],
    question: str,
    gateway: LLMGateway | None = None,
) -> DocumentQAResult:
    """`documents` must already be workspace-scoped, READY documents fetched
    by the caller (the API layer) — this function trusts the list it's
    given, it does not re-check tenancy (that's `DocumentRepository`'s job).
    """
    retriever = TenantDocumentRetriever(session, get_embedding_provider())
    document_ids = [d.id for d in documents]
    chunks = await retriever.retrieve(workspace_id=workspace_id, query_text=question, document_ids=document_ids, top_k=_TOP_K)

    if not chunks:
        return DocumentQAResult(status="insufficient_document_evidence")

    titles_by_document_id = {d.id: d.title for d in documents}
    chunks_by_index = {c.chunk_index: c for c in chunks}

    intent = _classify_question_intent(question)
    if intent is not None:
        extractive = _extractive_answer(intent, chunks, titles_by_document_id)
        if extractive is not None:
            extractive_answer, extractive_citations = extractive
            return DocumentQAResult(
                status="answered", answer=extractive_answer, citations=extractive_citations, answer_method="extractive"
            )

    evidence_text = "\n\n".join(
        f"[chunk {c.chunk_index}] (документ: {titles_by_document_id.get(c.document_id, '?')}, "
        f"{'стр. ' + str(c.page_number) if c.page_number else c.section_path or 'без разметки'}):\n{c.text}"
        for c in chunks
    )

    messages = [
        LLMMessage(
            role="user",
            content=f"Вопрос: {question}\n\n{wrap_untrusted('document_evidence', evidence_text)}",
        )
    ]

    llm = gateway or LLMGateway()
    result = await llm.structured_generate(
        TaskClass.EXTRACTION, messages, response_schema=_RESPONSE_SCHEMA, system=_SYSTEM_PROMPT
    )

    if not result.get("sufficient_evidence") or not result.get("answer"):
        return DocumentQAResult(status="insufficient_document_evidence")

    citations: list[DocumentCitation] = []
    for idx in result.get("cited_chunk_indices", []):
        chunk = chunks_by_index.get(idx)
        if chunk is None:
            continue  # never fabricate a citation pointing at a chunk that was never actually retrieved
        citations.append(
            DocumentCitation(
                citation_type="document_evidence",
                document_id=chunk.document_id,
                document_title=titles_by_document_id.get(chunk.document_id, "Документ"),
                page_number=chunk.page_number,
                section_path=chunk.section_path,
                excerpt=chunk.text[:_MAX_EXCERPT_CHARS],
                chunk_id=chunk.id,
                content_hash=chunk.content_hash,
            )
        )

    return DocumentQAResult(status="answered", answer=result["answer"], citations=citations, answer_method="llm")
