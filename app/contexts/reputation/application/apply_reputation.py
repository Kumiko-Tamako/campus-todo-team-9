"""声誉记账用例（分支 4，US-REP01）：事件载荷 → 幂等流水。

设计（3.6 细案 v3.1）：
- 上下文边界：reputation 对 qa **0 import**——事件经 DTO（VoteEventPayload/
  AcceptEventPayload）进入；发布端（qa interfaces）把领域事件序列化为 dict，
  worker 反序列化后构造 DTO。分派规则表（细案 G2）是记账口径唯一实现处。
- 自投不计分（裁定 3）：actor == 被记用户 → 跳过（返回 False，非错误）。
  选定 D-A'(i) 载荷补作者后判定无失败路径（G1 绑定注记）。
- 幂等：append_if_absent 以 (source, event_id) 复合唯一兜底，重复投递返回 False
  ——调用方视为成功 ack，不重试。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.contexts.reputation.application.ports import ReputationLedgerRepository
from app.contexts.reputation.domain.ledger import (
    ACCEPT_DELTA,
    ANSWER_DOWNVOTE_DELTA,
    ANSWER_UPVOTE_DELTA,
    QUESTION_DOWNVOTE_DELTA,
    QUESTION_UPVOTE_DELTA,
    LedgerEntry,
    LedgerSource,
)


@dataclass(frozen=True, slots=True)
class VoteEventPayload:
    """投票事件 DTO（来源：qa VoteCast 序列化；字段与领域事件一一对应）。"""

    vote_id: UUID
    user_id: UUID
    target_type: str
    target_id: UUID
    direction: str
    target_author_id: UUID
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class AcceptEventPayload:
    """采纳事件 DTO（来源：qa AnswerAccepted 序列化）。"""

    event_id: UUID
    answer_id: UUID
    answer_author_id: UUID
    occurred_at: datetime


# 分派规则表（细案 G2）：(target_type, direction) → (delta, reason)
_VOTE_DELTAS: dict[tuple[str, str], tuple[int, str]] = {
    ("answer", "up"): (ANSWER_UPVOTE_DELTA, "回答被赞"),
    ("answer", "down"): (ANSWER_DOWNVOTE_DELTA, "回答被踩"),
    ("question", "up"): (QUESTION_UPVOTE_DELTA, "问题被赞"),
    ("question", "down"): (QUESTION_DOWNVOTE_DELTA, "问题被踩"),
}


def vote_delta(target_type: str, direction: str) -> tuple[int, str]:
    """查分派表；未知组合（毒载荷）ValueError，由 worker 记日志丢弃不重试。"""
    try:
        return _VOTE_DELTAS[(target_type, direction)]
    except KeyError as exc:
        raise ValueError(f"未知的投票目标/方向: {target_type}/{direction}") from exc


async def apply_vote_event(
    payload: VoteEventPayload, repo: ReputationLedgerRepository
) -> bool:
    """投票事件记账：自投跳过 → 查分派表 → 幂等落流水。

    返回 True = 本调用实际写入；False = 自投跳过或事件已记账（均为成功语义）。
    """
    if payload.user_id == payload.target_author_id:
        return False  # 自投不计分（裁定 3）
    delta, reason = vote_delta(payload.target_type, payload.direction)
    entry = LedgerEntry(
        source=LedgerSource.VOTE,
        event_id=payload.vote_id,
        delta=delta,
        reason=reason,
        occurred_at=payload.occurred_at,
    )
    return await repo.append_if_absent(payload.target_author_id, entry)


async def apply_accept_event(
    payload: AcceptEventPayload, repo: ReputationLedgerRepository
) -> bool:
    """采纳事件记账：+15 记给回答作者（AnswerAccepted 自带作者，无需查库）。"""
    entry = LedgerEntry(
        source=LedgerSource.ACCEPT,
        event_id=payload.event_id,
        delta=ACCEPT_DELTA,
        reason="回答被采纳",
        occurred_at=payload.occurred_at,
    )
    return await repo.append_if_absent(payload.answer_author_id, entry)
