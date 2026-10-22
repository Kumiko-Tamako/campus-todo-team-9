"""关/编辑用例 + 既有用例关闭态拦截 单元测试：fake 仓储，不连库（进 CI）。

覆盖迭代 5（US-Q08/V02）用例编排：404→403→409 顺序、不变式透传、
PATCH 部分更新合并，以及 answer/vote/comment/accept 的"关闭=终态"拒绝（全冻结裁定）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.contexts.qa.application.accept_use_case import AcceptAnswerUseCase
from app.contexts.qa.application.answer_use_case import PostAnswerUseCase
from app.contexts.qa.application.close_question_use_case import CloseQuestionUseCase
from app.contexts.qa.application.commands import (
    AcceptAnswerCommand,
    CloseQuestionCommand,
    CreateCommentCommand,
    EditQuestionCommand,
    PostAnswerCommand,
    VoteOnCommand,
)
from app.contexts.qa.application.comment_use_case import CreateCommentUseCase
from app.contexts.qa.application.edit_question_use_case import EditQuestionUseCase
from app.contexts.qa.application.vote_use_case import VoteOnUseCase
from app.contexts.qa.domain.answer import Answer
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.errors import (
    AnswerAlreadyAcceptedError,
    NotQuestionAuthorError,
    QuestionAlreadyClosedError,
    QuestionClosedError,
    QuestionNotFoundError,
)
from app.contexts.qa.domain.question import Question, QuestionStatus
from app.contexts.qa.domain.repository import QuestionSort
from app.contexts.qa.domain.value_objects import Body, Title
from app.contexts.qa.domain.vote import Vote, VoteDirection, VoteTarget


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


class FakeVoteRepository:
    def __init__(self) -> None:
        self.added: list[Vote] = []

    async def find_by_user_target(
        self, user_id: UUID, target_type: VoteTarget, target_id: UUID
    ) -> Vote | None:
        return next(
            (
                v
                for v in self.added
                if v.user_id == user_id
                and v.target_type == target_type
                and v.target_id == target_id
            ),
            None,
        )

    async def add(self, vote: Vote) -> None:
        self.added.append(vote)


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


def _question(
    author_id: UUID | None = None, *, status: QuestionStatus = QuestionStatus.OPEN
) -> Question:
    return Question(
        id=uuid4(),
        title=Title("标题"),
        body=Body("正文"),
        author_id=author_id or uuid4(),
        created_at=datetime.now(UTC),
        status=status,
    )


def _answer(question_id: UUID) -> Answer:
    return Answer(
        id=uuid4(),
        question_id=question_id,
        author_id=uuid4(),
        body=Body("回答"),
        created_at=datetime.now(UTC),
    )


# ---------------- CloseQuestionUseCase ----------------


async def test_close_success_flips_status_and_updates() -> None:
    q_repo = FakeQuestionRepository()
    question = _question()
    q_repo.added = [question]

    result = await CloseQuestionUseCase(q_repo).execute(
        CloseQuestionCommand(question_id=question.id, actor_id=question.author_id)
    )

    assert result.status is QuestionStatus.CLOSED
    assert q_repo.updated == [question]


async def test_close_missing_question_404() -> None:
    q_repo = FakeQuestionRepository()
    with pytest.raises(QuestionNotFoundError):
        await CloseQuestionUseCase(q_repo).execute(
            CloseQuestionCommand(question_id=uuid4(), actor_id=uuid4())
        )
    assert q_repo.updated == []


async def test_close_by_non_author_403_and_state_kept() -> None:
    q_repo = FakeQuestionRepository()
    question = _question()
    q_repo.added = [question]
    with pytest.raises(NotQuestionAuthorError):
        await CloseQuestionUseCase(q_repo).execute(
            CloseQuestionCommand(question_id=question.id, actor_id=uuid4())
        )
    assert question.status is QuestionStatus.OPEN
    assert q_repo.updated == []


async def test_close_already_closed_409() -> None:
    q_repo = FakeQuestionRepository()
    question = _question(status=QuestionStatus.CLOSED)
    q_repo.added = [question]
    with pytest.raises(QuestionAlreadyClosedError):
        await CloseQuestionUseCase(q_repo).execute(
            CloseQuestionCommand(question_id=question.id, actor_id=question.author_id)
        )
    assert q_repo.updated == []


async def test_close_with_accepted_answer_409() -> None:
    q_repo = FakeQuestionRepository()
    question = _question()
    question.mark_accepted(uuid4())
    q_repo.added = [question]
    with pytest.raises(AnswerAlreadyAcceptedError):
        await CloseQuestionUseCase(q_repo).execute(
            CloseQuestionCommand(question_id=question.id, actor_id=question.author_id)
        )
    assert question.status is QuestionStatus.OPEN
    assert q_repo.updated == []


# ---------------- EditQuestionUseCase ----------------


async def test_edit_full_update() -> None:
    q_repo = FakeQuestionRepository()
    question = _question()
    q_repo.added = [question]

    result = await EditQuestionUseCase(q_repo).execute(
        EditQuestionCommand(
            question_id=question.id,
            actor_id=question.author_id,
            title="  新标题  ",
            body="新正文",
        )
    )

    assert result.title.value == "新标题"
    assert result.body.value == "新正文"
    assert q_repo.updated == [question]


async def test_edit_partial_title_only_keeps_body() -> None:
    q_repo = FakeQuestionRepository()
    question = _question()
    q_repo.added = [question]

    await EditQuestionUseCase(q_repo).execute(
        EditQuestionCommand(
            question_id=question.id, actor_id=question.author_id, title="新标题", body=None
        )
    )

    assert question.title.value == "新标题"
    assert question.body.value == "正文"  # 缺省侧沿用既有值
    assert q_repo.updated == [question]


async def test_edit_partial_body_only_keeps_title() -> None:
    q_repo = FakeQuestionRepository()
    question = _question()
    q_repo.added = [question]

    await EditQuestionUseCase(q_repo).execute(
        EditQuestionCommand(
            question_id=question.id, actor_id=question.author_id, title=None, body="新正文"
        )
    )

    assert question.title.value == "标题"
    assert question.body.value == "新正文"


async def test_edit_missing_question_404() -> None:
    q_repo = FakeQuestionRepository()
    with pytest.raises(QuestionNotFoundError):
        await EditQuestionUseCase(q_repo).execute(
            EditQuestionCommand(question_id=uuid4(), actor_id=uuid4(), title="新", body=None)
        )


async def test_edit_by_non_author_403() -> None:
    q_repo = FakeQuestionRepository()
    question = _question()
    q_repo.added = [question]
    with pytest.raises(NotQuestionAuthorError):
        await EditQuestionUseCase(q_repo).execute(
            EditQuestionCommand(
                question_id=question.id, actor_id=uuid4(), title="新标题", body=None
            )
        )
    assert question.title.value == "标题"
    assert q_repo.updated == []


async def test_edit_closed_409_and_no_write() -> None:
    q_repo = FakeQuestionRepository()
    question = _question(status=QuestionStatus.CLOSED)
    q_repo.added = [question]
    with pytest.raises(QuestionClosedError):
        await EditQuestionUseCase(q_repo).execute(
            EditQuestionCommand(
                question_id=question.id, actor_id=question.author_id, title="新标题", body=None
            )
        )
    assert q_repo.updated == []


async def test_edit_invalid_value_422_semantics_and_no_write() -> None:
    q_repo = FakeQuestionRepository()
    question = _question()
    q_repo.added = [question]
    with pytest.raises(ValueError):
        await EditQuestionUseCase(q_repo).execute(
            EditQuestionCommand(
                question_id=question.id, actor_id=question.author_id, title=None, body="   "
            )
        )
    assert q_repo.updated == []


# ---------------- 既有用例的关闭态拦截（全冻结） ----------------


async def test_post_answer_on_closed_rejected() -> None:
    q_repo, a_repo = FakeQuestionRepository(), FakeAnswerRepository()
    question = _question(status=QuestionStatus.CLOSED)
    q_repo.added = [question]
    with pytest.raises(QuestionClosedError):
        await PostAnswerUseCase(q_repo, a_repo).execute(
            PostAnswerCommand(question_id=question.id, body="回答", author_id=uuid4())
        )
    assert a_repo.added == []


async def test_vote_question_closed_rejected() -> None:
    q_repo, a_repo, v_repo = FakeQuestionRepository(), FakeAnswerRepository(), FakeVoteRepository()
    question = _question(status=QuestionStatus.CLOSED)
    q_repo.added = [question]
    with pytest.raises(QuestionClosedError):
        await VoteOnUseCase(q_repo, a_repo, v_repo).execute(
            VoteOnCommand(
                target_type=VoteTarget.QUESTION,
                target_id=question.id,
                direction=VoteDirection.UP,
                user_id=uuid4(),
            )
        )
    assert v_repo.added == []


async def test_vote_answer_on_closed_parent_rejected() -> None:
    q_repo, a_repo, v_repo = FakeQuestionRepository(), FakeAnswerRepository(), FakeVoteRepository()
    question = _question(status=QuestionStatus.CLOSED)
    answer = _answer(question.id)
    q_repo.added = [question]
    a_repo.added = [answer]
    with pytest.raises(QuestionClosedError):
        await VoteOnUseCase(q_repo, a_repo, v_repo).execute(
            VoteOnCommand(
                target_type=VoteTarget.ANSWER,
                target_id=answer.id,
                direction=VoteDirection.UP,
                user_id=uuid4(),
            )
        )
    assert v_repo.added == []


async def test_comment_question_closed_rejected() -> None:
    q_repo, a_repo, c_repo = (
        FakeQuestionRepository(),
        FakeAnswerRepository(),
        FakeCommentRepository(),
    )
    question = _question(status=QuestionStatus.CLOSED)
    q_repo.added = [question]
    with pytest.raises(QuestionClosedError):
        await CreateCommentUseCase(q_repo, a_repo, c_repo).execute(
            CreateCommentCommand(
                target_type=CommentTarget.QUESTION,
                target_id=question.id,
                body="评论",
                author_id=uuid4(),
            )
        )
    assert c_repo.added == []


async def test_comment_answer_on_closed_parent_rejected() -> None:
    q_repo, a_repo, c_repo = (
        FakeQuestionRepository(),
        FakeAnswerRepository(),
        FakeCommentRepository(),
    )
    question = _question(status=QuestionStatus.CLOSED)
    answer = _answer(question.id)
    q_repo.added = [question]
    a_repo.added = [answer]
    with pytest.raises(QuestionClosedError):
        await CreateCommentUseCase(q_repo, a_repo, c_repo).execute(
            CreateCommentCommand(
                target_type=CommentTarget.ANSWER,
                target_id=answer.id,
                body="评论",
                author_id=uuid4(),
            )
        )
    assert c_repo.added == []


async def test_accept_on_closed_rejected() -> None:
    q_repo, a_repo = FakeQuestionRepository(), FakeAnswerRepository()
    question = _question(status=QuestionStatus.CLOSED)
    answer = _answer(question.id)
    q_repo.added = [question]
    a_repo.added = [answer]
    with pytest.raises(QuestionClosedError):
        await AcceptAnswerUseCase(q_repo, a_repo).execute(
            AcceptAnswerCommand(answer_id=answer.id, actor_id=question.author_id)
        )
    assert answer.is_accepted is False
    assert q_repo.updated == [] and a_repo.updated == []