"""Aggregates every /api/v1/legal/* router — see LEGAL-API.md for the full contract."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, auth, cases, chat, companies, contracts, documents, knowledge, research

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(research.router)
api_router.include_router(contracts.router)
api_router.include_router(cases.router)
api_router.include_router(companies.router)
api_router.include_router(documents.router)
api_router.include_router(knowledge.router)
api_router.include_router(admin.router)
