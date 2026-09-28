"""ReputationLedger 聚合单元测试：fake 无库（进 CI）。

覆盖不变式：delta≠0 校验、只追加、event_id 幂等拒绝（同 source 拒/异 source 允）、
total=流水累加（可为负）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.contexts.reputation.domain.ledger import (
    ACCEPT_DELTA,
    LedgerEntry,
    LedgerSource,
    ReputationChanged,
    ReputationLedger,
)


def _entry(source: LedgerSource = LedgerSource.VOTE, delta: int = 10) -> LedgerEntry:
    return LedgerEntry(
        source=source,
        event_id=uuid4(),
        delta=delta,
        reason="测试事由",
        occurred_at=datetime.now(UTC),
    )


def test_ledger_entry_zero_delta_rejected() -> None:
    """流水行 delta=0 无意义（既非加分也非扣分），域内拒绝。"""
    with pytest.raises(ValueError, match="变动值"):
        _entry(delta=0)


def test_record_appends_and_total_sums() -> None:
    """追加流水，total = 累加（含负分）。"""
    ledger = ReputationLedger(user_id=uuid4())
    ledger.record(_entry(delta=10))
    ledger.record(_entry(source=LedgerSource.ACCEPT, delta=ACCEPT_DELTA))
    ledger.record(_entry(delta=-2))
    assert ledger.total == 10 + ACCEPT_DELTA - 2
    assert len(ledger.entries) == 3


def test_record_duplicate_same_source_rejected() -> None:
    """不变式 1：同 (source, event_id) 重复记账拒绝（幂等）。"""
    ledger = ReputationLedger(user_id=uuid4())
    entry = _entry(delta=10)
    ledger.record(entry)
    duplicate = LedgerEntry(
        source=entry.source,
        event_id=entry.event_id,
        delta=10,
        reason="重放",
        occurred_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="已记过账"):
        ledger.record(duplicate)


def test_record_same_event_id_different_source_allowed() -> None:
    """异源 UUID 语义隔离：同 event_id 不同 source 视为不同事件。"""
    ledger = ReputationLedger(user_id=uuid4())
    event_id = uuid4()
    ledger.record(
        LedgerEntry(
            source=LedgerSource.VOTE,
            event_id=event_id,
            delta=10,
            reason="回答被赞",
            occurred_at=datetime.now(UTC),
        )
    )
    ledger.record(
        LedgerEntry(
            source=LedgerSource.ACCEPT,
            event_id=event_id,
            delta=ACCEPT_DELTA,
            reason="回答被采纳",
            occurred_at=datetime.now(UTC),
        )
    )
    assert len(ledger.entries) == 2


def test_reputation_changed_event_carries_fields() -> None:
    """ReputationChanged 定义留位（无订阅者）：字段可构造即可。"""
    event = ReputationChanged(
        user_id=uuid4(), delta=ACCEPT_DELTA, event_id=uuid4(), occurred_at=datetime.now(UTC)
    )
    assert event.delta == ACCEPT_DELTA
