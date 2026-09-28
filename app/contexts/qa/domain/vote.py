from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class VoteTarget(StrEnum):
    """投票目标类型：问题 / 回答（1.3 功能域 7）。"""

    QUESTION = "question"
    ANSWER = "answer"


class VoteDirection(StrEnum):
    """投票方向：赞成 / 反对（1.3 L144"投赞成或反对票"）。"""

    UP = "up"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class VoteCast:
    """领域事件：一票已投出。

    由 VoteOnUseCase 投票成功即发（v3 自裁：Vote 为独立值对象 + 独立仓储，
    事件由应用层用例代发）；分支 4 声誉消费方经 Celery 消费（US-REP01）。
    载荷自足（3.6 细案 v3.1 D-A'(i)）：vote_id 作幂等键（票行主键、不可改票）、
    user_id 供自投判断、target_author_id 供记分定位（worker 零查库）。
    """

    vote_id: UUID
    user_id: UUID
    target_type: VoteTarget
    target_id: UUID
    direction: VoteDirection
    target_author_id: UUID
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class Vote:
    """投票值对象（冻结，不可改票——v3 裁定 #5：再次投票一律 409）。

    一人一票为集合级不变式：仓储 find_by_user_target 事前检查 +
    库级复合唯一索引 (user_id, target_type, target_id) 兜底，不分方向。
    """

    id: UUID
    user_id: UUID
    target_type: VoteTarget
    target_id: UUID
    direction: VoteDirection
    created_at: datetime

    @classmethod
    def cast(
        cls,
        *,
        user_id: UUID,
        target_type: VoteTarget,
        target_id: UUID,
        direction: VoteDirection,
    ) -> Vote:
        """工厂：投出一票。非法方向值在枚举构造处即拒绝（ValueError）。"""
        return cls(
            id=uuid4(),
            user_id=user_id,
            target_type=VoteTarget(target_type),
            direction=VoteDirection(direction),
            target_id=target_id,
            created_at=datetime.now(UTC),
        )

    def cast_event(self, *, target_author_id: UUID) -> VoteCast:
        """本票对应的领域事件载荷（用例在投票成功后发出）。

        target_author_id 由用例从已加载的目标聚合提取（载荷自足，D-A'(i)）。
        """
        return VoteCast(
            vote_id=self.id,
            user_id=self.user_id,
            target_type=self.target_type,
            target_id=self.target_id,
            direction=self.direction,
            target_author_id=target_author_id,
            occurred_at=self.created_at,
        )
