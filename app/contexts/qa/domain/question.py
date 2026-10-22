from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.contexts.qa.domain.errors import (
    AnswerAlreadyAcceptedError,
    QuestionAlreadyClosedError,
    QuestionClosedError,
)
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


@dataclass(frozen=True, slots=True)
class QuestionClosed:
    """领域事件：问题被提问者关闭（US-Q08；V02 关闭禁投的触发动作）。

    迭代 5 无订阅者；照发留位（与 QuestionPublished 同模式）。
    """

    question_id: UUID
    author_id: UUID
    occurred_at: datetime


class QuestionStatus(StrEnum):
    """问题生命周期状态（US-Q08）：关闭为终态，backlog 无重开故事（2026-09-29 裁定全冻结）。"""

    OPEN = "open"
    CLOSED = "closed"


@dataclass
class Question:
    """Question 聚合根（迭代 3：+ accepted_answer_id；迭代 4：+ tags；迭代 5：+ status 关闭态）。"""

    id: UUID
    title: Title
    body: Body
    author_id: UUID
    created_at: datetime
    accepted_answer_id: UUID | None = None
    status: QuestionStatus = QuestionStatus.OPEN
    tags: list[Tag] = field(default_factory=list)
    events: list[QuestionPublished | QuestionClosed] = field(
        default_factory=list, repr=False, compare=False
    )

    def mark_accepted(self, answer_id: UUID) -> None:
        """记录采纳答案引用（US-V03 跨聚合双写的本侧；幂等检查在应用层）。"""
        self.accepted_answer_id = answer_id

    def close(self) -> None:
        """关闭问题（US-Q08）：重复关闭→409；已采纳答案→409（不变式 5：已采纳不可关闭）。

        关闭为终态（2026-09-29 裁定全冻结）：此后编辑/新增回答/投票/评论/采纳
        一律拒绝，无重开故事。
        """
        if self.status is QuestionStatus.CLOSED:
            raise QuestionAlreadyClosedError("问题已关闭")
        if self.accepted_answer_id is not None:
            raise AnswerAlreadyAcceptedError("该问题已有采纳答案，不可关闭")
        self.status = QuestionStatus.CLOSED
        self.events.append(
            QuestionClosed(
                question_id=self.id,
                author_id=self.author_id,
                occurred_at=datetime.now(UTC),
            )
        )

    def edit_title_body(self, *, title_value: str, body_value: str) -> None:
        """编辑标题+正文（US-Q08；裁定 D6 仅标题+正文，标签不可编辑）。

        已关闭问题不可编辑（QuestionClosedError→409，全冻结裁定）；
        值对象先构后赋——任一校验失败（ValueError→422）不产生半改状态。
        """
        if self.status is QuestionStatus.CLOSED:
            raise QuestionClosedError("已关闭的问题不可编辑")
        title = Title(title_value)
        body = Body(body_value)
        self.title = title
        self.body = body

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