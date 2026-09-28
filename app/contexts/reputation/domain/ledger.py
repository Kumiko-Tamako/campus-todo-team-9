"""ReputationLedger 聚合：声誉流水（分支 4，US-REP01/REP02）。

设计要点（aggregates.md 第 6 节定稿 + 3.6 细案 v3.1 裁定）：
- 按用户一本账；账面总值 = 流水累加，不落总值列（不变式 3，防旁路改账）；
- 流水行只追加不修改（不变式 2，审计要求）；
- event_id 幂等：库级 (source, event_id) 复合唯一索引兜底（不变式 1）——
  vote 侧 event_id = 票行主键 vote_id（不可改票，复投 409），accept 侧 =
  事件 uuid4（一答一采纳，重复采纳 409）；两异源 UUID 以 source 隔离语义；
- 分值常量为唯一出处（答辩引用同源）：回答被赞 +10 / 被踩 -2、问题被赞 +5 /
  被踩 -2、被采纳 +15；自投（actor == 被记用户）不计分——SO 惯例简化版（裁定 3）。

上下文边界：本模块不 import qa——事件载荷以应用层 DTO（VoteEventPayload/
AcceptEventPayload）进入，见 application/apply_reputation.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class LedgerSource(StrEnum):
    """流水来源事件类型（(source, event_id) 复合唯一索引的第一键）。"""

    VOTE = "vote"
    ACCEPT = "accept"


# 分值常量（SO 惯例简化版，v3.1 裁定 3）——声誉口径唯一出处
ANSWER_UPVOTE_DELTA = 10
ANSWER_DOWNVOTE_DELTA = -2
QUESTION_UPVOTE_DELTA = 5
QUESTION_DOWNVOTE_DELTA = -2
ACCEPT_DELTA = 15


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """流水行：一次声誉变动（只追加，审计不可变）。"""

    source: LedgerSource
    event_id: UUID
    delta: int
    reason: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.delta == 0:
            raise ValueError("声誉变动值不能为 0")


@dataclass
class ReputationLedger:
    """声誉账本聚合根（按用户一本账）。

    record 的聚合内查重是快速失败路径；并发重复投递由库级唯一索引
    (source, event_id) 兜底（仓储 ON CONFLICT DO NOTHING，恰一行）。
    """

    user_id: UUID
    entries: list[LedgerEntry] = field(default_factory=list, repr=False, compare=False)

    @property
    def total(self) -> int:
        """账面声誉值 = 流水累加（可为负：踩分计入）。"""
        return sum(e.delta for e in self.entries)

    def record(self, entry: LedgerEntry) -> None:
        """追加一条流水；同 (source, event_id) 重复拒绝（不变式 1）。"""
        if any(
            e.source == entry.source and e.event_id == entry.event_id for e in self.entries
        ):
            raise ValueError("该事件已记过账")
        self.entries.append(entry)


@dataclass(frozen=True, slots=True)
class ReputationChanged:
    """领域事件：账本新增流水（aggregates.md 定稿的发布事件）。

    迭代 4 无订阅者，定义留位不派发（通知/排行归后续迭代，台账登记该偏差）。
    """

    user_id: UUID
    delta: int
    event_id: UUID
    occurred_at: datetime
