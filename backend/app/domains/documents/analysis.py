"""Document analysis — Phase 9.2 brief §20. Every extracted fact carries a
provenance category (brief: "Разделять EXTRACTED / INFERRED / UNVERIFIED"):

  EXTRACTED — found by a deterministic regex directly in the document text.
    Never wrong about *presence* (it's a literal string match), though a
    regex can still misclassify (e.g. a date-shaped number that isn't a
    real date) — that risk is inherent to any deterministic extraction and
    is why this stays clearly labeled EXTRACTED, not "verified truth".
  INFERRED — produced by the LLM, grounded in (and citing) the retrieved
    document evidence. Under LLM_PROVIDER=mock this is always empty — the
    mock provider returns schema-valid empty defaults, never a fabricated
    conclusion (app/llm/providers/mock_provider.py).
  UNVERIFIED — reserved for anything that doesn't cleanly fit either
    bucket; not populated by this implementation (nothing here currently
    produces a claim it can't place in EXTRACTED or INFERRED), but kept in
    the result shape so a future extractor has somewhere honest to put one
    rather than force-fitting it into EXTRACTED.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.shared.legal_patterns import AMOUNT as _AMOUNT
from app.domains.shared.legal_patterns import DATE_NUMERIC as _DATE_NUMERIC
from app.domains.shared.legal_patterns import DATE_WORDY as _DATE_WORDY
from app.domains.shared.legal_patterns import PARTY_ENTITY as _PARTY_ENTITY
from app.domains.shared.legal_patterns import PARTY_ROLE as _PARTY_ROLE
from app.llm.base import LLMMessage
from app.llm.prompt_safety import UNTRUSTED_CONTENT_NOTICE, wrap_untrusted
from app.llm.routing.gateway import LLMGateway, TaskClass
from app.models.matters import Document, DocumentChunk

_DOCUMENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "Договор оказания услуг": ["оказани", "услуг"],
    "Договор поставки": ["поставк"],
    "Договор аренды": ["аренд"],
    "NDA / Соглашение о конфиденциальности": ["конфиденциальност", "nda"],
    "Претензия": ["претензи"],
    "Доверенность": ["доверенност"],
}


@dataclass
class ExtractedFact:
    value: str
    provenance: str
    kind: str  # "date" | "amount" | "party"


@dataclass
class DocumentAnalysisResult:
    status: str  # "analyzed" | "insufficient_document_evidence"
    document_type_extracted: str | None = None  # EXTRACTED — deterministic keyword match against document text
    extracted_dates: list[ExtractedFact] = field(default_factory=list)
    extracted_amounts: list[ExtractedFact] = field(default_factory=list)
    extracted_parties: list[ExtractedFact] = field(default_factory=list)
    inferred_obligations: list[str] = field(default_factory=list)
    inferred_risks: list[str] = field(default_factory=list)
    inferred_missing_information: list[str] = field(default_factory=list)


def _provenance_for(chunk: DocumentChunk) -> str:
    if chunk.section_path:
        return chunk.section_path
    if chunk.page_number:
        return f"стр. {chunk.page_number}"
    return f"chunk {chunk.chunk_index}"


def _extract_deterministic_facts(chunks: list[DocumentChunk]) -> tuple[list[ExtractedFact], list[ExtractedFact], list[ExtractedFact]]:
    dates: list[ExtractedFact] = []
    amounts: list[ExtractedFact] = []
    parties: list[ExtractedFact] = []
    seen_dates: set[str] = set()
    seen_amounts: set[str] = set()
    seen_parties: set[str] = set()

    for chunk in chunks:
        provenance = _provenance_for(chunk)
        for match in _DATE_NUMERIC.finditer(chunk.text):
            if match.group(0) not in seen_dates:
                seen_dates.add(match.group(0))
                dates.append(ExtractedFact(match.group(0), provenance, "date"))
        for match in _DATE_WORDY.finditer(chunk.text):
            if match.group(0) not in seen_dates:
                seen_dates.add(match.group(0))
                dates.append(ExtractedFact(match.group(0), provenance, "date"))
        for match in _AMOUNT.finditer(chunk.text):
            if match.group(0) not in seen_amounts:
                seen_amounts.add(match.group(0))
                amounts.append(ExtractedFact(match.group(0), provenance, "amount"))
        for match in _PARTY_ENTITY.finditer(chunk.text):
            value = match.group(0)
            if value not in seen_parties:
                seen_parties.add(value)
                parties.append(ExtractedFact(value, provenance, "party"))
        for match in _PARTY_ROLE.finditer(chunk.text):
            value = f"{match.group(1)}: {match.group(2).strip()}"
            if value not in seen_parties:
                seen_parties.add(value)
                parties.append(ExtractedFact(value, provenance, "party"))

    return dates, amounts, parties


def _detect_document_type(text: str) -> str | None:
    lowered = text.lower()
    for label, keywords in _DOCUMENT_TYPE_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return label
    return None


_INFERENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "obligations": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["obligations", "risks", "missing_information"],
}

_SYSTEM_PROMPT = (
    "You are a legal document analysis assistant. Based ONLY on the document text provided below, "
    "list contractual obligations, potential legal/commercial risks, and any important missing "
    "information (e.g. an undated signature block, a missing party's details). Never invent details "
    "not present in the text. " + UNTRUSTED_CONTENT_NOTICE
)


async def analyze_document(
    *,
    document: Document,
    chunks: list[DocumentChunk],
    gateway: LLMGateway | None = None,
) -> DocumentAnalysisResult:
    if not chunks:
        return DocumentAnalysisResult(status="insufficient_document_evidence")

    dates, amounts, parties = _extract_deterministic_facts(chunks)
    document_type = _detect_document_type(document.extracted_text or "")

    full_text = "\n\n".join(c.text for c in chunks)
    messages = [LLMMessage(role="user", content=wrap_untrusted("document_text", full_text))]
    llm = gateway or LLMGateway()
    inference = await llm.structured_generate(
        TaskClass.EXTRACTION, messages, response_schema=_INFERENCE_SCHEMA, system=_SYSTEM_PROMPT
    )

    return DocumentAnalysisResult(
        status="analyzed",
        document_type_extracted=document_type,
        extracted_dates=dates,
        extracted_amounts=amounts,
        extracted_parties=parties,
        inferred_obligations=inference.get("obligations", []),
        inferred_risks=inference.get("risks", []),
        inferred_missing_information=inference.get("missing_information", []),
    )
