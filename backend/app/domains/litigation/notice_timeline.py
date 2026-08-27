"""Demand/notice timeline extraction (P0 reasoning primitive). Extracts
whether a pre-suit demand letter was actually delivered, using the generic
status vocabulary of Russian Post (Почта России) tracking reports — a
standardized public tracking format, not specific to any one case or
company, that frequently gets attached as an exhibit to Russian civil
claims to prove pre-suit demand was sent.

Never infers delivery merely from the existence of a demand letter. If no
tracking report is present in the document text, the result says so
explicitly (`UNKNOWN`) rather than assuming either outcome. If a tracking
report is present, the final status is read off the LAST chronological
tracking event (Russian Post reports list events oldest-first), classified
into one of a small set of generic buckets by keyword — never by guessing
at a specific date, since OCR frequently drops the day-of-month digit from
these reports' timestamp column (a real, repeatedly observed corruption in
this package) leaving the event's own date unparseable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

_TRACKING_REPORT_MARKER = re.compile(r"Почт[ыа]\s+России", re.IGNORECASE)
_TRACKING_NUMBER = re.compile(r"почтовым\s+идентификатором\D{0,15}(\d{10,20})", re.IGNORECASE)

# Ordered worst-to-best is not meaningful here; classification is by keyword,
# independent per event line. "notice_left" (a slip saying mail is waiting)
# is deliberately distinct from "delivered" (the item itself handed over) —
# conflating them would let an unclaimed letter masquerade as received.
_RETURNED_MARKERS = (
    "выслано обратно отправителю",
    "срок хранения истек",
    "возврат отправителю",
    "отказ от получения",
    "не вручено",
)
_NOTICE_LEFT_MARKERS = ("направлено извещение", "вручено извещение")
# Requires the complete word "вручено"/"вручена" (not just the "вручен-"
# stem) so this doesn't false-match inside unrelated words sharing the same
# stem, e.g. "место вручения" ("delivery location", a noun phrase — not a
# delivered-status event).
_DELIVERED_MARKER = re.compile(r"\bвручен[оа]\b(?!\s+извещени)", re.IGNORECASE)
_IN_TRANSIT_MARKERS = ("прибыло в сортировочный", "покинуло", "сортировка", "прибыло в место вручения")
_DISPATCHED_MARKERS = ("принято в отделении связи", "присвоен трек-номер")

_STATUS_LINE = re.compile(r"^.{0,40}?(?:\d{1,2}[:.]\d{2}|\d{4})[^\n]{0,120}$", re.MULTILINE)
_LAST_NUMERIC_DATE_BEFORE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def _classify_line(line: str) -> str | None:
    lowered = line.lower()
    if any(marker in lowered for marker in _RETURNED_MARKERS):
        return "RETURNED"
    if any(marker in lowered for marker in _NOTICE_LEFT_MARKERS):
        return "NOTICE_LEFT"
    if _DELIVERED_MARKER.search(lowered):
        return "DELIVERED"
    if any(marker in lowered for marker in _IN_TRANSIT_MARKERS):
        return "IN_TRANSIT"
    if any(marker in lowered for marker in _DISPATCHED_MARKERS):
        return "DISPATCHED"
    return None


@dataclass
class NoticeEvent:
    raw_text: str
    category: str  # DISPATCHED | IN_TRANSIT | NOTICE_LEFT | DELIVERED | RETURNED


@dataclass
class NoticeTimelineResult:
    tracking_report_present: bool
    tracking_number: str | None
    demand_date: date | None
    events: list[NoticeEvent] = field(default_factory=list)
    final_status: str = "UNKNOWN"  # DISPATCHED | IN_TRANSIT | NOTICE_LEFT | DELIVERED | RETURNED | UNKNOWN
    final_status_explanation: str = ""


def _extract_demand_date(text: str, tracking_start: int | None) -> date | None:
    """The demand letter's own signing/dispatch date — the last standalone
    numeric date appearing before the tracking report begins (or anywhere
    in the text if no tracking report is present). Deliberately does not
    attempt to parse per-event dates inside the tracking report itself: this
    package has repeatedly observed OCR dropping the day-of-month digit from
    that report's own timestamp column, which would otherwise silently
    produce a wrong date rather than an honest "unavailable."
    """
    window = text[:tracking_start] if tracking_start is not None else text
    matches = list(_LAST_NUMERIC_DATE_BEFORE.finditer(window))
    if not matches:
        return None
    day, month, year = matches[-1].groups()
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def extract_notice_timeline(document_text: str) -> NoticeTimelineResult:
    tracking_match = _TRACKING_REPORT_MARKER.search(document_text)

    if tracking_match is None:
        return NoticeTimelineResult(
            tracking_report_present=False,
            tracking_number=None,
            demand_date=_extract_demand_date(document_text, None),
            events=[],
            final_status="UNKNOWN",
            final_status_explanation="No Russian Post tracking report was found in this document's text.",
        )

    tracking_number_match = _TRACKING_NUMBER.search(document_text)
    tracking_number = tracking_number_match.group(1) if tracking_number_match else None
    demand_date = _extract_demand_date(document_text, tracking_match.start())

    events: list[NoticeEvent] = []
    for line_match in _STATUS_LINE.finditer(document_text):
        line = line_match.group(0)
        category = _classify_line(line)
        if category is not None:
            events.append(NoticeEvent(raw_text=line.strip(), category=category))

    if not events:
        return NoticeTimelineResult(
            tracking_report_present=True,
            tracking_number=tracking_number,
            demand_date=demand_date,
            events=[],
            final_status="UNKNOWN",
            final_status_explanation="A tracking report was found but no recognized status event could be classified from it.",
        )

    # A definitive terminal outcome (RETURNED, then DELIVERED) outranks any
    # later event, rather than naively trusting whichever event is last in
    # the report: once an item is marked returned-to-sender, the report
    # keeps logging further transit events for the RETURN shipment itself
    # moving back — those later "in transit" lines describe the return
    # journey, not a reversal of the non-delivery outcome, and must not
    # overwrite it.
    categories_present = {e.category for e in events}
    priority = ("RETURNED", "DELIVERED", "NOTICE_LEFT", "IN_TRANSIT", "DISPATCHED")
    final_status = next(status for status in priority if status in categories_present)
    explanations = {
        "RETURNED": (
            "The tracking report shows the item was ultimately returned to sender / storage period expired — "
            "the addressee never actually took possession of it, on this record."
        ),
        "DELIVERED": "The tracking report shows the item was delivered to the addressee.",
        "NOTICE_LEFT": (
            "The tracking report shows only that a delivery notice/slip was left for the addressee — this is "
            "not the same as the addressee receiving the demand letter itself."
        ),
        "IN_TRANSIT": "The tracking report's last recorded event shows the item still in transit; no final delivery outcome is recorded.",
        "DISPATCHED": "The tracking report shows only that the item was dispatched; no further delivery outcome is recorded.",
    }
    return NoticeTimelineResult(
        tracking_report_present=True,
        tracking_number=tracking_number,
        demand_date=demand_date,
        events=events,
        final_status=final_status,
        final_status_explanation=explanations.get(final_status, ""),
    )
