"""记账用例单元测试：fake 仓储，不连库（进 CI）。

覆盖分派规则表（细案 G2）全矩阵 + 自投跳过 + 毒载荷拒绝 + 幂等返回值透传。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.contexts.reputation.application.apply_reputation import (
    AcceptEventPayload,
    VoteEventPayload,
    apply_accept_event,
    apply_vote_event,
    vote_delta,
)
from app.contexts.reputation.domain.ledger import (
    ACCEPT_DELTA,
    LedgerEntry,
    LedgerSource,
)


class FakeLedgerRepository:
    """假仓储：记录调用，可编程命中（已记账）。"""

    def __init__(self, hit: bool = False) -> None:
        self.calls: list[tuple[UUID, LedgerEntry]] = []
        self._hit = hit

    async def append_if_absent(self, user_id: UUID, entry: LedgerEntry) -> bool:
        self.calls.append((user_id, entry))
        return not self._hit

    async def total(self, user_id: UUID) -> int:
        return 0

    async def entries_desc(self, user_id: UUID) -> list[LedgerEntry]:
        return []


def _vote_payload(
    *,
    user_id: UUID | None = None,
    target_type: str = "answer",
    direction: str = "up",
    target_author_id: UUID | None = None,
) -> VoteEventPayload:
    return VoteEventPayload(
        vote_id=uuid4(),
        user_id=user_id or uuid4(),
        target_type=target_type,
        target_id=uuid4(),
        direction=direction,
        target_author_id=target_author_id or uuid4(),
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    ("target_type", "direction", "expected_delta"),
    [
        ("answer", "up", 10),
        ("answer", "down", -2),
        ("question", "up", 5),
        ("question", "down", -2),
    ],
)
async def test_vote_event_dispatch_matrix(
    target_type: str, direction: str, expected_delta: int
) -> None:
    """分派规则表：赞/踩 × 问题/回答 → (delta, 被记用户=target_author)。"""
    payload = _vote_payload(target_type=target_type, direction=direction)
    repo = FakeLedgerRepository()
    recorded = await apply_vote_event(payload, repo)  # type: ignore[arg-type]
    assert recorded is True
    assert len(repo.calls) == 1
    credited_user, entry = repo.calls[0]
    assert credited_user == payload.target_author_id  # 记给作者而非投票者
    assert entry.delta == expected_delta
    assert entry.source is LedgerSource.VOTE
    assert entry.event_id == payload.vote_id  # 幂等键 = 票行主键


async def test_self_vote_skipped_without_entry() -> None:
    """自投不计分（裁定 3）：跳过且不产生流水，返回 False（成功语义非错误）。"""
    author = uuid4()
    payload = _vote_payload(user_id=author, target_author_id=author)
    repo = FakeLedgerRepository()
    recorded = await apply_vote_event(payload, repo)  # type: ignore[arg-type]
    assert recorded is False
    assert repo.calls == []


@pytest.mark.parametrize(
    ("target_type", "direction"), [("course", "up"), ("answer", "sideways")]
)
async def test_unknown_target_or_direction_rejected(
    target_type: str, direction: str
) -> None:
    """毒载荷：未知组合 ValueError（worker 不重试，记日志丢弃）。"""
    with pytest.raises(ValueError, match="未知"):
        vote_delta(target_type, direction)


async def test_accept_event_credits_answer_author() -> None:
    """采纳 +15 记给回答作者（AnswerAccepted 自带作者，无需查库）。"""
    payload = AcceptEventPayload(
        event_id=uuid4(),
        answer_id=uuid4(),
        answer_author_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )
    repo = FakeLedgerRepository()
    recorded = await apply_accept_event(payload, repo)  # type: ignore[arg-type]
    assert recorded is True
    credited_user, entry = repo.calls[0]
    assert credited_user == payload.answer_author_id
    assert entry.delta == ACCEPT_DELTA
    assert entry.source is LedgerSource.ACCEPT
    assert entry.event_id == payload.event_id


async def test_already_recorded_returns_false() -> None:
    """仓储判重命中（重放事件）→ False 透传，调用方视为成功 ack。"""
    payload = _vote_payload()
    repo = FakeLedgerRepository(hit=True)
    recorded = await apply_vote_event(payload, repo)  # type: ignore[arg-type]
    assert recorded is False
    assert len(repo.calls) == 1  # 查询发生了，只是没写入
