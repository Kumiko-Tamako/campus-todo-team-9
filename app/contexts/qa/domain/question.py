from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.contexts.qa.domain.value_objects import Body, Title


@dataclass(frozen=True, slots=True)
class QuestionPublished:
    """领域事件：问题发布完成。

    迭代 1 无订阅者（发布即可见 = 提交即读，US-Q04）；
    事件照聚合规范照发，为阶段 3 事件总线（声誉/通知）留位。
    """

    question_id: UUID
    author_id: UUID
    occurred_at: datetime


@dataclass
class Question:
    """Question 聚合根（迭代 1：标题 + 正文 + 作者引用，暂不含 Vote/Comment）。"""

    id: UUID
    title: Title
    body: Body
    author_id: UUID
    created_at: datetime
    events: list[QuestionPublished] = field(default_factory=list, repr=False, compare=False)

    @classmethod
    def ask(cls, *, title_value: str, body_value: str, author_id: UUID) -> Question:
        """工厂：发布问题。值对象即校验（标题/正文非空且长度合法），并发布 QuestionPublished。"""
        now = datetime.now(UTC)
        question = cls(
            id=uuid4(),
            title=Title(title_value),
            body=Body(body_value),
            author_id=author_id,
            created_at=now,
        )
        question.events.append(
            QuestionPublished(question_id=question.id, author_id=author_id, occurred_at=now)
        )
        return question
