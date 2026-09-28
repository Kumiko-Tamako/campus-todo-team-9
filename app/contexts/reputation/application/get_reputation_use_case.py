"""声誉查询用例（分支 4，US-REP02）：总值 + 时间倒序流水。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.contexts.reputation.application.ports import ReputationLedgerRepository
from app.contexts.reputation.domain.ledger import LedgerEntry


@dataclass(frozen=True, slots=True)
class ReputationView:
    """声誉视图：账面总值（流水累加）+ 倒序流水（Gherkin 功能域 11 场景 3）。"""

    user_id: UUID
    total: int
    entries: list[LedgerEntry]


class GetReputationUseCase:
    """查询声誉：total 与 entries 两次读取非同一快照（课程规模可接受，无跨行事务需求）。"""

    def __init__(self, repository: ReputationLedgerRepository) -> None:
        self._repository = repository

    async def execute(self, user_id: UUID) -> ReputationView:
        total = await self._repository.total(user_id)
        entries = await self._repository.entries_desc(user_id)
        return ReputationView(user_id=user_id, total=total, entries=entries)
