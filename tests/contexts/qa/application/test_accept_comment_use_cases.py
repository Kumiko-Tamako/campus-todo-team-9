"""AcceptAnswerUseCase / CreateCommentUseCase 单元测试：fake 仓储，不连库（进 CI）。

覆盖计划分支 2 用例：仅提问者 403 / 回答不存在 404 / 重复采纳 409 / 双写两侧 /
评论目标存在 / 正文校验 / 题评答评分组。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.contexts.qa.application.accept_use_case import AcceptAnswerUseCase
from app.contexts.qa.application.commands import AcceptAnswerCommand, CreateCommentCommand
from app.contexts.qa.application.comment_use_case import CreateCommentUseCase
from app.contexts.qa.domain.answer import Answer
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.errors import (
    AnswerAlreadyAcceptedError,
    AnswerNotFoundError,
    NotQuestionAuthorError,
    QuestionNotFoundError,
)
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import QuestionSort
from app.contexts.qa.domain.value_objects import Body, Title


class FakeQuestionRepository:
    def __init__(self) -> None:
        self.added: list[Question] = []
        self.updated: list[Question] = []

    async def add(self, question: Question) -> None:
        self.added.append(question)

    async def update(self, question: Question) -> None:
        self.updated.append(question)

    async def get_by_id(self, question_id: UUID) -> Question | None:
        return next((q for q in self.added if q.id == question_id), None)

    async def list_paginated(
        self, page: int, page_size: int, sort: QuestionSort = QuestionSort.LATEST
    ) -> tuple[list[Question], int]:
        return self.added, len(self.added)


class FakeAnswerRepository:
    def __init__(self) -> None:
        self.added: list[Answer] = []
        self.updated: list[Answer] = []

    async def add(self, answer: Answer) -> None:
        self.added.append(answer)

    async def update(self, answer: Answer) -> None:
        self.updated.append(answer)

    async def get_by_id(self, answer_id: UUID) -> Answer | None:
        return next((a for a in self.added if a.id == answer_id), None)

    async def list_by_question(self, question_id: UUID) -> list[Answer]:
        return [a for a in self.added if a.question_id == question_id]


class FakeCommentRepository:
    def __init__(self) -> None:
        self.added: list[Comment] = []

    async def add(self, comment: Comment) -> None:
        self.added.append(comment)

    async def list_by_target(
        self, target_type: CommentTarget, target_id: UUID
    ) -> list[Comment]:
        return [
            c for c in self.added if c.target_type == target_type and c.target_id == target_id
        ]


def _question(author_id: UUID | None = None) -> Question:
    return Question(
        id=uuid4(),
        title=Title("标题"),
        body=Body("正文"),
        author_id=author_id or uuid4(),
        created_at=datetime.now(UTC),
    )


def _answer(question_id: UUID) -> Answer:
    return Answer(
        id=uuid4(),
        question_id=question_id,
        author_id=uuid4(),
        body=Body("回答"),
        created_at=datetime.now(UTC),
    )


# ---------------- AcceptAnswerUseCase ----------------


async def test_accept_writes_both_sides_and_emits_event() -> None:
    q_repo, a_repo = FakeQuestionRepository(), FakeAnswerRepository()
    question = _question()
    q_repo.added = [question]
    answer = _answer(question.id)
    a_repo.added = [answer]

    outcome = await AcceptAnswerUseCase(q_repo, a_repo).execute(
        AcceptAnswerCommand(answer_id=answer.id, actor_id=question.author_id)
    )

    assert answer.is_accepted is True  # Answer 侧翻转
    assert question.accepted_answer_id == answer.id  # Question 侧双写
    assert a_repo.updated == [answer]
    assert q_repo.updated == [question]
    assert outcome.event.answer_id == answer.id
    assert outcome.event.question_id == question.id
    assert outcome.event.answer_author_id == answer.author_id
    assert outcome.event.accepted_by == question.author_id


async def test_accept_missing_answer_404() -> None:
    q_repo, a_repo = FakeQuestionRepository(), FakeAnswerRepository()
    with pytest.raises(AnswerNotFoundError):
        await AcceptAnswerUseCase(q_repo, a_repo).execute(
            AcceptAnswerCommand(answer_id=uuid4(), actor_id=uuid4())
        )
    assert a_repo.updated == [] and q_repo.updated == []


async def test_accept_by_non_author_403() -> None:
    q_repo, a_repo = FakeQuestionRepository(), FakeAnswerRepository()
    question = _question()
    q_repo.added = [question]
    answer = _answer(question.id)
    a_repo.added = [answer]

    with pytest.raises(NotQuestionAuthorError):
        await AcceptAnswerUseCase(q_repo, a_repo).execute(
            AcceptAnswerCommand(answer_id=answer.id, actor_id=uuid4())  # 非提问者
        )
    assert answer.is_accepted is False
    assert q_repo.updated == [] and a_repo.updated == []


async def test_reaccept_rejected_409_even_same_answer() -> None:
    """一题一采纳：已有 accepted_answer_id 再采纳（含同一答案）一律 409（计划 L73）。"""
    q_repo, a_repo = FakeQuestionRepository(), FakeAnswerRepository()
    question = _question()
    first = _answer(question.id)
    second = _answer(question.id)
    question.accepted_answer_id = first.id
    q_repo.added = [question]
    a_repo.added = [first, second]

    with pytest.raises(AnswerAlreadyAcceptedError):
        await AcceptAnswerUseCase(q_repo, a_repo).execute(
            AcceptAnswerCommand(answer_id=first.id, actor_id=question.author_id)
        )
    with pytest.raises(AnswerAlreadyAcceptedError):
        await AcceptAnswerUseCase(q_repo, a_repo).execute(
            AcceptAnswerCommand(answer_id=second.id, actor_id=question.author_id)
        )


# ---------------- CreateCommentUseCase ----------------


async def test_comment_on_question_persists_and_emits() -> None:
    q_repo, a_repo, c_repo = (
        FakeQuestionRepository(),
        FakeAnswerRepository(),
        FakeCommentRepository(),
    )
    question = _question()
    q_repo.added = [question]
    author = uuid4()

    comment = await CreateCommentUseCase(q_repo, a_repo, c_repo).execute(
        CreateCommentCommand(
            target_type=CommentTarget.QUESTION,
            target_id=question.id,
            body="  可以参考教材第 3 章  ",
            author_id=author,
        )
    )

    assert c_repo.added == [comment]
    assert comment.target_type is CommentTarget.QUESTION
    assert comment.body.value == "可以参考教材第 3 章"  # strip 规范化
    assert comment.author_id == author
    assert len(comment.events) == 1
    assert comment.events[0].comment_id == comment.id


async def test_comment_on_answer_persists() -> None:
    q_repo, a_repo, c_repo = (
        FakeQuestionRepository(),
        FakeAnswerRepository(),
        FakeCommentRepository(),
    )
    question = _question()
    answer = _answer(question.id)
    q_repo.added = [question]
    a_repo.added = [answer]

    comment = await CreateCommentUseCase(q_repo, a_repo, c_repo).execute(
        CreateCommentCommand(
            target_type=CommentTarget.ANSWER,
            target_id=answer.id,
            body="补充说明",
            author_id=uuid4(),
        )
    )
    assert comment.target_type is CommentTarget.ANSWER
    assert c_repo.added == [comment]


async def test_comment_missing_targets_raise_404() -> None:
    q_repo, a_repo, c_repo = (
        FakeQuestionRepository(),
        FakeAnswerRepository(),
        FakeCommentRepository(),
    )
    with pytest.raises(QuestionNotFoundError):
        await CreateCommentUseCase(q_repo, a_repo, c_repo).execute(
            CreateCommentCommand(
                target_type=CommentTarget.QUESTION,
                target_id=uuid4(),
                body="x",
                author_id=uuid4(),
            )
        )
    with pytest.raises(AnswerNotFoundError):
        await CreateCommentUseCase(q_repo, a_repo, c_repo).execute(
            CreateCommentCommand(
                target_type=CommentTarget.ANSWER,
                target_id=uuid4(),
                body="x",
                author_id=uuid4(),
            )
        )
    assert c_repo.added == []


async def test_comment_blank_body_raises_and_persists_nothing() -> None:
    q_repo, a_repo, c_repo = (
        FakeQuestionRepository(),
        FakeAnswerRepository(),
        FakeCommentRepository(),
    )
    question = _question()
    q_repo.added = [question]
    with pytest.raises(ValueError):
        await CreateCommentUseCase(q_repo, a_repo, c_repo).execute(
            CreateCommentCommand(
                target_type=CommentTarget.QUESTION,
                target_id=question.id,
                body="   ",
                author_id=uuid4(),
            )
        )
    assert c_repo.added == []


# ---------------- Comment 工厂枚举即校验 ----------------


def test_comment_write_rejects_invalid_target_type() -> None:
    with pytest.raises(ValueError):
        Comment.write(
            target_type="vote",  # type: ignore[arg-type]
            target_id=uuid4(),
            author_id=uuid4(),
            body_value="正文",
        )
