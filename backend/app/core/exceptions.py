"""App-wide exception types. Kept small and explicit — no bare Exception catches at the API boundary."""
from __future__ import annotations


class LegalAIBureauError(Exception):
    """Base class for all application-raised errors."""


class NotFoundError(LegalAIBureauError):
    pass


class TenantIsolationViolation(LegalAIBureauError):
    """Raised when a query would cross a workspace boundary. Should never be caught and swallowed."""


class UnverifiedCitationError(LegalAIBureauError):
    """Raised when a flow requires a verified citation but validation failed (LEGAL-RAG.md §4)."""
