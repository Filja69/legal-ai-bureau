from __future__ import annotations

from app.models.contracts import Contract, ContractClause, ContractRisk, ContractVersion
from app.repositories.base import WorkspaceScopedRepository


class ContractRepository(WorkspaceScopedRepository[Contract]):  # type: ignore[type-var]
    model = Contract


class ContractVersionRepository(WorkspaceScopedRepository[ContractVersion]):  # type: ignore[type-var]
    model = ContractVersion


class ContractClauseRepository(WorkspaceScopedRepository[ContractClause]):  # type: ignore[type-var]
    model = ContractClause


class ContractRiskRepository(WorkspaceScopedRepository[ContractRisk]):  # type: ignore[type-var]
    model = ContractRisk
