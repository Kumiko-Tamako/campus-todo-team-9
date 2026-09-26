from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.contexts.qa.domain.value_objects import Body


class CommentTarget(StrEnum):
    """评论目标类型：题评挂 Question、答评挂 Answer（aggregates.md L17）。

    与 VoteTarget 值域相同但语义独立，各聚合各自持有，不跨模块耦合。
    """

    QUESTION = "question"
    ANSWER = "answer"


@dataclass(frozen=True, slots=True)
class CommentCreated:
    """领域事件：评论发布完成（US-C01）。

    迭代 3 无订阅者；照聚合规范照发，为事件总线留位。
    """

    comment_id: UUID
    target_type: CommentTarget
    target_id: UUID
    author_id: UUID
    occurred_at: datetime


@dataclass
class Comment:
    """评论实体（aggregates.md L17：题评归属 Question 聚合、答评归属 Answer 聚合）。

    建模与 Vote 同模式：独立仓储 + 多态 target（target_type + target_id），
    避免第三聚合；生命周期跟随宿主。
    正文复用 Body 值对象（1~5000 字，strip 规范化）——v3 自裁：1.3 未单独定义评论长度。
    """

    id: UUID
    target_type: CommentTarget
    target_id: UUID
    author_id: UUID
    body: Body
    created_at: datetime
    events: list[CommentCreated] = field(default_factory=list, repr=False, compare=False)

    @classmethod
    def write(
        cls,
        *,
        target_type: CommentTarget,
        target_id: UUID,
        author_id: UUID,
        body_value: str,
    ) -> Comment:
        """工厂：发表评论。Body 值对象即校验，并发布 CommentCreated。"""
        now = datetime.now(UTC)
        comment = cls(
            id=uuid4(),
            target_type=CommentTarget(target_type),
            target_id=target_id,
            author_id=author_id,
            body=Body(body_value),
            created_at=now,
        )
        comment.events.append(
            CommentCreated(
                comment_id=comment.id,
                target_type=CommentTarget(target_type),
                target_id=target_id,
                author_id=author_id,
                occurred_at=now,
            )
        )
        return comment

