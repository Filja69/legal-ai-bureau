#!/usr/bin/env python3
"""Read-only connectivity proof for publication.pravo.gov.ru's documented
API — run from a GitHub-hosted Actions runner, a network path distinct
from Railway/this repo's local sandbox (both confirmed blocked — see
docs/LEGAL-SOURCE-MATRIX.md §4/§Phase 6-8). STEP 1 only: prove reachability
and the real response shape. No DB writes, no secrets, no proxy/VPN, no
bulk fetch — three bounded GET requests, sanitized output only.

Endpoints (LEGAL-SOURCE-MATRIX.md + the portal's own /help docs):
  - PublicBlocks — publication block/sub-block listing
  - Categories   — category listing
  - Documents    — the documented search endpoint, called here with the
    smallest possible page (CurrentPageNumber=1, RangeSize=1) purely to
    observe the response contract, not to retrieve real content.

Never prints a full raw response body to the job log (only a small,
allowlisted set of metadata fields) — the bounded raw preview kept in the
artifact JSON exists solely so a human can later confirm the parsed
summary matches reality, and is capped at MAX_PREVIEW_CHARS regardless.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

USER_AGENT = "LegalAIBureau-Ingestion/0.1"
TIMEOUT_SECONDS = 20
MAX_PREVIEW_CHARS = 500
RESULTS_PATH = "pravo-connectivity-results.json"

ENDPOINTS = {
    "public_blocks": "https://publication.pravo.gov.ru/api/PublicBlocks/",
    "categories": "https://publication.pravo.gov.ru/api/Categories",
    "documents_search": "https://publication.pravo.gov.ru/api/Documents?CurrentPageNumber=1&RangeSize=1",
}

# Small, named allowlist — never the whole record, so nothing resembling
# real document text ever lands in the log or the artifact by accident.
_SAFE_FIELD_NAMES = {
    "id", "name", "title", "code", "shortName", "fullName", "count", "total",
    "pageCount", "documentDate", "signDate", "pubDate", "number", "eoNumber",
}


@dataclass
class EndpointResult:
    name: str
    request_url: str
    reachable: bool
    status_code: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    byte_length: int | None = None
    json_type: str | None = None
    top_level_keys: list[str] = field(default_factory=list)
    safe_metadata_preview: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    raw_body_preview: str | None = None


def _safe_preview(obj: dict[str, Any], limit: int = 8) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for key, value in obj.items():
        if key in _SAFE_FIELD_NAMES and not isinstance(value, dict | list):
            preview[key] = value
        if len(preview) >= limit:
            break
    return preview


def check_endpoint(name: str, url: str) -> EndpointResult:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read()
            status_code = response.status
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type")
    except urllib.error.HTTPError as exc:
        # A real HTTP error response still proves the host is reachable —
        # captured, not treated as a connectivity failure.
        body = exc.read() if exc.fp else b""
        status_code = exc.code
        final_url = getattr(exc, "geturl", lambda: url)()
        content_type = exc.headers.get("Content-Type") if exc.headers else None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return EndpointResult(name=name, request_url=url, reachable=False, error=f"{type(exc).__name__}: {exc}")

    result = EndpointResult(
        name=name,
        request_url=url,
        reachable=True,
        status_code=status_code,
        final_url=final_url,
        content_type=content_type,
        byte_length=len(body),
        raw_body_preview=body[:MAX_PREVIEW_CHARS].decode("utf-8", errors="replace"),
    )

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return result

    if isinstance(parsed, dict):
        result.json_type = "object"
        result.top_level_keys = list(parsed.keys())[:20]
        result.safe_metadata_preview = _safe_preview(parsed)
    elif isinstance(parsed, list):
        result.json_type = "array"
        result.top_level_keys = [f"array of {len(parsed)} items"]
        if parsed and isinstance(parsed[0], dict):
            result.safe_metadata_preview = _safe_preview(parsed[0])
    else:
        result.json_type = type(parsed).__name__

    return result


def main() -> int:
    results = [check_endpoint(name, url) for name, url in ENDPOINTS.items()]

    print("=" * 70)
    print("publication.pravo.gov.ru -- connectivity proof (STEP 1, read-only)")
    print("=" * 70)
    any_reachable = False
    for r in results:
        print(f"\n[{r.name}] {r.request_url}")
        if not r.reachable:
            print(f"  UNREACHABLE -- {r.error}")
            continue
        any_reachable = True
        print(f"  status_code:    {r.status_code}")
        print(f"  final_url:      {r.final_url}")
        print(f"  content_type:   {r.content_type}")
        print(f"  byte_length:    {r.byte_length}")
        print(f"  json_type:      {r.json_type}")
        print(f"  top_level_keys: {r.top_level_keys}")
        print(f"  safe_metadata:  {r.safe_metadata_preview}")

    print("\n" + "=" * 70)
    print(f"RESULT: {'AT LEAST ONE ENDPOINT REACHABLE' if any_reachable else 'ALL ENDPOINTS UNREACHABLE'}")
    print("=" * 70)

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)

    # Always exits 0 -- this is a one-time investigative connectivity proof,
    # not a recurring health check. Unreachability is a valid, informative
    # outcome to record, not a workflow failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())
