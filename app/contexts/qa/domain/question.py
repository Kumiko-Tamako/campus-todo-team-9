from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.contexts.qa.domain.tag import Tag
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
    """Question 聚合根（迭代 3：+ accepted_answer_id 采纳引用；迭代 4：+ tags 值对象集合）。"""

    id: UUID
    title: Title
    body: Body
    author_id: UUID
    created_at: datetime
    accepted_answer_id: UUID | None = None
    tags: list[Tag] = field(default_factory=list)
    events: list[QuestionPublished] = field(default_factory=list, repr=False, compare=False)

    def mark_accepted(self, answer_id: UUID) -> None:
        """记录采纳答案引用（US-V03 跨聚合双写的本侧；幂等检查在应用层）。"""
        self.accepted_answer_id = answer_id

    @classmethod
    def ask(
        cls,
        *,
        title_value: str,
        body_value: str,
        author_id: UUID,
        tags: list[Tag] | None = None,
    ) -> Question:
        """工厂：发布问题。值对象即校验（标题/正文非空且长度合法），并发布 QuestionPublished。

        tags 由用例经 TagCatalog.resolve 解析（去重 + ≤5 上限已在目录侧强制，Q03）。
        """
        now = datetime.now(UTC)
        question = cls(
            id=uuid4(),
            title=Title(title_value),
            body=Body(body_value),
            author_id=author_id,
            created_at=now,
            tags=list(tags) if tags else [],
        )
        question.events.append(
            QuestionPublished(question_id=question.id, author_id=author_id, occurred_at=now)
        )
        return question
