"""ReputationLedger 仓储集成测试：真 PostgreSQL。

覆盖：ON CONFLICT 幂等（同 (source, event_id) 恰一行、异 source 同 event_id 两行）、
SUM 总值（空 0/含负分）、occurred_at 倒序 + id tiebreaker。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.contexts.reputation.domain.ledger import LedgerEntry, LedgerSource
from app.contexts.reputation.infrastructure.repository import (
    SqlAlchemyReputationLedgerRepository,
)
from app.shared.engine import session_factory

pytestmark = pytest.mark.integration


async def _make_user() -> uuid.UUID:
    """造一个真实用户（FK 需要）。"""
    from app.contexts.identity.application.commands import RegisterCommand
    from app.contexts.identity.application.register_use_case import RegisterUseCase
    from app.contexts.identity.infrastructure.password_hasher import BcryptPasswordHasher
    from app.contexts.identity.infrastructure.repository import SqlAlchemyUserRepository

    async with session_factory() as session:
        use_case = RegisterUseCase(SqlAlchemyUserRepository(session), BcryptPasswordHasher())
        user = await use_case.execute(
            RegisterCommand(
                role="student",
                email=f"{uuid.uuid4()}@stu.edu.cn",
                password="Passw0rd8",
                student_id=str(uuid.uuid4().int)[:10],
            )
        )
        await session.commit()
        return user.id


def _entry(source: LedgerSource, delta: int, at: datetime) -> LedgerEntry:
    return LedgerEntry(
        source=source,
        event_id=uuid.uuid4(),
        delta=delta,
        reason="集成测试",
        occurred_at=at,
    )


async def test_append_if_absent_idempotent_single_row() -> None:
    """同 (source, event_id) 二次追加 → False，库中恰一行。"""
    user_id = await _make_user()
    entry = _entry(LedgerSource.VOTE, 10, datetime.now(UTC))
    async with session_factory() as session:
        repo = SqlAlchemyReputationLedgerRepository(session)
        assert await repo.append_if_absent(user_id, entry) is True
        assert await repo.append_if_absent(user_id, entry) is False  # 幂等跳过
        await session.commit()
        assert await repo.total(user_id) == 10
        assert len(await repo.entries_desc(user_id)) == 1


async def test_same_event_id_different_source_two_rows() -> None:
    """异源语义隔离：同 event_id 不同 source → 各记一行。"""
    user_id = await _make_user()
    event_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with session_factory() as session:
        repo = SqlAlchemyReputationLedgerRepository(session)
        vote_entry = LedgerEntry(
            source=LedgerSource.VOTE,
            event_id=event_id,
            delta=10,
            reason="回答被赞",
            occurred_at=now,
        )
        accept_entry = LedgerEntry(
            source=LedgerSource.ACCEPT,
            event_id=event_id,
            delta=15,
            reason="回答被采纳",
            occurred_at=now,
        )
        assert await repo.append_if_absent(user_id, vote_entry) is True
        assert await repo.append_if_absent(user_id, accept_entry) is True
        await session.commit()
        assert await repo.total(user_id) == 25


async def test_total_empty_is_zero_and_negative_sums() -> None:
    """无流水 total=0；踩分可为负（SO 惯例：净分展示）。"""
    user_id = await _make_user()
    now = datetime.now(UTC)
    async with session_factory() as session:
        repo = SqlAlchemyReputationLedgerRepository(session)
        assert await repo.total(user_id) == 0
        await repo.append_if_absent(user_id, _entry(LedgerSource.VOTE, -2, now))
        await repo.append_if_absent(user_id, _entry(LedgerSource.VOTE, 10, now))
        await session.commit()
        assert await repo.total(user_id) == 8


async def test_entries_desc_orders_by_occurred_at() -> None:
    """倒序：新事件在前；同刻事件以 id 倒序 tiebreaker（确定性全序）。"""
    user_id = await _make_user()
    base = datetime.now(UTC)
    async with session_factory() as session:
        repo = SqlAlchemyReputationLedgerRepository(session)
        old = _entry(LedgerSource.VOTE, 5, base - timedelta(hours=2))
        new = _entry(LedgerSource.VOTE, 10, base)
        await repo.append_if_absent(user_id, old)
        await repo.append_if_absent(user_id, new)
        await session.commit()
        entries = await repo.entries_desc(user_id)
        assert [e.event_id for e in entries] == [new.event_id, old.event_id]
