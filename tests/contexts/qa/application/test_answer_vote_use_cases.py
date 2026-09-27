"""PostAnswerUseCase / VoteOnUseCase 单元测试：fake 仓储，不连库（进 CI）。

排序/去重的 SQL 行为在仓储实现层，集成层覆盖；本层验证用例编排与不变式前置检查。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.contexts.qa.application.answer_use_case import PostAnswerUseCase
from app.contexts.qa.application.commands import PostAnswerCommand, VoteOnCommand
from app.contexts.qa.application.vote_use_case import VoteOnUseCase
from app.contexts.qa.domain.answer import Answer
from app.contexts.qa.domain.errors import (
    AlreadyVotedError,
    AnswerNotFoundError,
    QuestionNotFoundError,
)
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import QuestionSort
from app.contexts.qa.domain.value_objects import Body, Title
from app.contexts.qa.domain.vote import Vote, VoteDirection, VoteTarget


class FakeQuestionRepository:
    def __init__(self) -> None:
        self.added: list[Question] = []

    async def add(self, question: Question) -> None:
        self.added.append(question)

    async def get_by_id(self, question_id: UUID) -> Question | None:
        return next((q for q in self.added if q.id == question_id), None)

    async def list_paginated(
        self, page: int, page_size: int, sort: QuestionSort = QuestionSort.LATEST
    ) -> tuple[list[Question], int]:
        return self.added, len(self.added)


class FakeAnswerRepository:
    def __init__(self) -> None:
        self.added: list[Answer] = []

    async def add(self, answer: Answer) -> None:
        self.added.append(answer)

    async def get_by_id(self, answer_id: UUID) -> Answer | None:
        return next((a for a in self.added if a.id == answer_id), None)

    async def list_by_question(self, question_id: UUID) -> list[Answer]:
        return [a for a in self.added if a.question_id == question_id]


class FakeVoteRepository:
    def __init__(self) -> None:
        self.added: list[Vote] = []

    async def find_by_user_target(
        self, user_id: UUID, target_type: VoteTarget, target_id: UUID
    ) -> Vote | None:
        return next(
            (v for v in self.added if v.user_id == user_id and v.target_type == target_type
             and v.target_id == target_id),
            None,
        )

    async def add(self, vote: Vote) -> None:
        self.added.append(vote)


def _question() -> Question:
    from datetime import UTC, datetime

    return Question(
        id=uuid4(),
        title=Title("标题"),
        body=Body("正文"),
        author_id=uuid4(),
        created_at=datetime.now(UTC),
    )


# ---------------- PostAnswerUseCase ----------------


async def test_post_answer_persists_with_command_fields() -> None:
    q_repo, a_repo = FakeQuestionRepository(), FakeAnswerRepository()
    question = _question()
    q_repo.added = [question]
    author = uuid4()

    result = await PostAnswerUseCase(q_repo, a_repo).execute(
        PostAnswerCommand(question_id=question.id, body="  回答正文  ", author_id=author)
    )

    assert a_repo.added == [result]
    assert result.question_id == question.id
    assert result.author_id == author
    assert result.body.value == "回答正文"  # 值对象已规范化
    assert result.is_accepted is False


async def test_post_answer_missing_question_raises_404_semantics() -> None:
    q_repo, a_repo = FakeQuestionRepository(), FakeAnswerRepository()
    with pytest.raises(QuestionNotFoundError):
        await PostAnswerUseCase(q_repo, a_repo).execute(
            PostAnswerCommand(question_id=uuid4(), body="正文", author_id=uuid4())
        )
    assert a_repo.added == []  # 目标不存在不落库


async def test_post_answer_invalid_body_raises_and_persists_nothing() -> None:
    q_repo, a_repo = FakeQuestionRepository(), FakeAnswerRepository()
    q_repo.added = [_question()]
    with pytest.raises(ValueError):
        await PostAnswerUseCase(q_repo, a_repo).execute(
            PostAnswerCommand(question_id=q_repo.added[0].id, body="   ", author_id=uuid4())
        )
    assert a_repo.added == []


# ---------------- VoteOnUseCase ----------------


# ---------------- Vote 枚举校验（计划步骤 5 单元项） ----------------


def test_vote_cast_rejects_invalid_direction_and_target() -> None:
    """非法方向/目标类型在枚举构造处即 ValueError（422 语义来源）。"""
    with pytest.raises(ValueError):
        Vote.cast(
            user_id=uuid4(),
            target_type=VoteTarget.QUESTION,
            target_id=uuid4(),
            direction="sideways",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        Vote.cast(
            user_id=uuid4(),
            target_type="comment",  # type: ignore[arg-type]
            target_id=uuid4(),
            direction=VoteDirection.UP,
        )


async def test_vote_on_question_casts_vote_and_emits_event() -> None:
    q_repo, a_repo, v_repo = FakeQuestionRepository(), FakeAnswerRepository(), FakeVoteRepository()
    question = _question()
    q_repo.added = [question]
    user = uuid4()

    outcome = await VoteOnUseCase(q_repo, a_repo, v_repo).execute(
        VoteOnCommand(
            target_type=VoteTarget.QUESTION,
            target_id=question.id,
            direction=VoteDirection.UP,
            user_id=user,
        )
    )

    assert v_repo.added == [outcome.vote]
    assert outcome.vote.direction is VoteDirection.UP
    assert outcome.event.target_id == question.id
    assert outcome.event.user_id == user
    assert outcome.event.direction is VoteDirection.UP


async def test_vote_on_missing_question_raises_404() -> None:
    q_repo, a_repo, v_repo = FakeQuestionRepository(), FakeAnswerRepository(), FakeVoteRepository()
    with pytest.raises(QuestionNotFoundError):
        await VoteOnUseCase(q_repo, a_repo, v_repo).execute(
            VoteOnCommand(
                target_type=VoteTarget.QUESTION,
                target_id=uuid4(),
                direction=VoteDirection.DOWN,
                user_id=uuid4(),
            )
        )
    assert v_repo.added == []


async def test_vote_on_missing_answer_raises_404() -> None:
    q_repo, a_repo, v_repo = FakeQuestionRepository(), FakeAnswerRepository(), FakeVoteRepository()
    with pytest.raises(AnswerNotFoundError):
        await VoteOnUseCase(q_repo, a_repo, v_repo).execute(
            VoteOnCommand(
                target_type=VoteTarget.ANSWER,
                target_id=uuid4(),
                direction=VoteDirection.UP,
                user_id=uuid4(),
            )
        )


async def test_revote_raises_already_voted_and_persists_nothing() -> None:
    """v3 裁定 #5：不可改票——已有票再投（即使换方向）一律 AlreadyVotedError。"""
    q_repo, a_repo, v_repo = FakeQuestionRepository(), FakeAnswerRepository(), FakeVoteRepository()
    question = _question()
    q_repo.added = [question]
    user = uuid4()
    v_repo.added = [
        Vote.cast(
            user_id=user,
            target_type=VoteTarget.QUESTION,
            target_id=question.id,
            direction=VoteDirection.UP,
        )
    ]

    with pytest.raises(AlreadyVotedError):
        await VoteOnUseCase(q_repo, a_repo, v_repo).execute(
            VoteOnCommand(
                target_type=VoteTarget.QUESTION,
                target_id=question.id,
                direction=VoteDirection.DOWN,  # 改投反对同样被拒
                user_id=user,
            )
        )
    assert len(v_repo.added) == 1  # 未追加新票
