from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.contexts.qa.domain.value_objects import Body


@dataclass(frozen=True, slots=True)
class AnswerPosted:
    """领域事件：回答发布完成。

    迭代 2 无订阅者；照聚合规范照发，为阶段 3 事件总线（声誉/通知）留位。
    """

    answer_id: UUID
    question_id: UUID
    author_id: UUID
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class AnswerAccepted:
    """领域事件：回答被采纳（US-V03 → 声誉联动 US-REP01，分支 4 消费）。

    由 AcceptAnswerUseCase 在采纳成功（跨聚合双写提交）后发出——与 VoteCast 同模式：
    采纳是应用层编排的跨聚合行为，事件由用例代发（v3 自裁）。
    event_id 为幂等键（uuid4，采纳事务内生成一次；重复采纳 409 保证一答一事件），
    分支 4 以 (source, event_id) 复合唯一记账（v3.1 裁定 1a）。
    """

    event_id: UUID
    answer_id: UUID
    question_id: UUID
    answer_author_id: UUID
    accepted_by: UUID
    occurred_at: datetime


@dataclass
class Answer:
    """Answer 聚合根（迭代 2：正文 + 问题/作者引用）。

    votes_count 为读时聚合字段（净票数 up − down，v3 裁定 #1），由仓储重建时填入；
    is_accepted 本迭代恒 False，采纳行为随分支 2 的 accept() 落地。
    """

    id: UUID
    question_id: UUID
    author_id: UUID
    body: Body
    created_at: datetime
    is_accepted: bool = False
    votes_count: int = 0
    events: list[AnswerPosted] = field(default_factory=list, repr=False, compare=False)

    @classmethod
    def post(cls, *, question_id: UUID, author_id: UUID, body_value: str) -> Answer:
        """工厂：发布回答。值对象即校验（正文非空且长度合法），并发布 AnswerPosted。"""
        now = datetime.now(UTC)
        answer = cls(
            id=uuid4(),
            question_id=question_id,
            author_id=author_id,
            body=Body(body_value),
            created_at=now,
        )
        answer.events.append(
            AnswerPosted(
                answer_id=answer.id,
                question_id=question_id,
                author_id=author_id,
                occurred_at=now,
            )
        )
        return answer

    def accept(self) -> None:
        """标记为已采纳（US-V03）。

        幂等检查（重复采纳→409）在应用层编排（需读 Question.accepted_answer_id
        判"该问题是否已有采纳答案"），本方法只做状态翻转；
        被采纳回答不可删除（V03）由删除路径在落地时强制（本阶段无删除用例）。
        """
        self.is_accepted = True
