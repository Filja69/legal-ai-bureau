"""Seeds the deterministic mock contract dataset (brief §69) into a workspace —
used by tests and the eval suite. Always `is_mock=True`, never mistaken for
a real uploaded contract downstream (mirrors the LegalSource.is_mock
convention from LEGAL-SOURCES.md).
"""
from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.contracts.mock_contracts import MOCK_CONTRACTS
from app.models.contracts import Contract, ContractType, ContractTypeSource, ContractVersion


async def seed_mock_contracts(session: AsyncSession, workspace_id: uuid.UUID) -> dict[str, tuple[Contract, ContractVersion]]:
    created: dict[str, tuple[Contract, ContractVersion]] = {}
    for record in MOCK_CONTRACTS:
        contract = Contract(
            workspace_id=workspace_id, title=record["title"], contract_type=ContractType(record["contract_type"]),
            contract_type_source=ContractTypeSource.USER_CONFIRMED, is_mock=True,
        )
        session.add(contract)
        await session.flush()

        content_hash = hashlib.sha256(record["text"].encode("utf-8")).hexdigest()
        version = ContractVersion(
            workspace_id=workspace_id, contract_id=contract.id, version_number=1,
            content=record["text"], content_hash=content_hash, is_current=True,
        )
        session.add(version)
        await session.flush()

        created[record["key"]] = (contract, version)
    return created
