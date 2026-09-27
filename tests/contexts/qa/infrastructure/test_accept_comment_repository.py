"""CommentRepository 集成测试 + 采纳双写回读（分支 2 步骤 5）：真 PostgreSQL。

覆盖：评论落库回读、题评/答评分组、时间正序；采纳 update 两侧落库与重建
（accepted_answer_id / is_accepted 跨会话回读）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.contexts.identity.application.commands import RegisterCommand
from app.contexts.identity.application.register_use_case import RegisterUseCase
from app.contexts.identity.infrastructure.password_hasher import BcryptPasswordHasher
from app.contexts.identity.infrastructure.repository import SqlAlchemyUserRepository
from app.contexts.qa.application.accept_use_case import AcceptAnswerUseCase
from app.contexts.qa.application.commands import AcceptAnswerCommand
from app.contexts.qa.domain.answer import Answer
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.value_objects import Body, Title
from app.contexts.qa.infrastructure.repository import (
    SqlAlchemyAnswerRepository,
    SqlAlchemyCommentRepository,
    SqlAlchemyQuestionRepository,
)
from app.shared.engine import session_factory

pytestmark = pytest.mark.integration

_BASE = datetime(2017, 1, 1, tzinfo=UTC)  # 足够旧：不进入任何"最新"断言窗口


async def _make_author() -> uuid.UUID:
    async with session_factory() as session:
        use_case = RegisterUseCase(SqlAlchemyUserRepository(session), BcryptPasswordHasher())
        user = await use_case.execute(
            RegisterCommand(
                role="student",
                email=f"{uuid.uuid4()}@stu.edu.cn",
                password="Passw0rd8",
                student_id=str(uuid.uuid4().int)[:10],
            )
        )
        await session.commit()
        return user.id


def _question(author_id: uuid.UUID) -> Question:
    return Question(
        id=uuid.uuid4(),
        title=Title(f"采纳评论仓储 {uuid.uuid4().hex[:8]}"),
        body=Body("正文"),
        author_id=author_id,
        created_at=_BASE,
    )


def _answer(question_id: uuid.UUID, author_id: uuid.UUID, *, at: datetime) -> Answer:
    return Answer(
        id=uuid.uuid4(),
        question_id=question_id,
        author_id=author_id,
        body=Body("回答正文"),
        created_at=at,
    )


def _comment(
    target_type: CommentTarget, target_id: uuid.UUID, author_id: uuid.UUID, *, at: datetime
) -> Comment:
    return Comment(
        id=uuid.uuid4(),
        target_type=target_type,
        target_id=target_id,
        author_id=author_id,
        body=Body("评论正文"),
        created_at=at,
    )


async def test_comment_persists_and_lists_in_time_order() -> None:
    author = await _make_author()
    q = _question(author)
    c1 = _comment(CommentTarget.QUESTION, q.id, author, at=_BASE + timedelta(seconds=2))
    c2 = _comment(CommentTarget.QUESTION, q.id, author, at=_BASE + timedelta(seconds=1))
    foreign = _comment(CommentTarget.QUESTION, uuid.uuid4(), author, at=_BASE)
    async with session_factory() as session:
        await SqlAlchemyQuestionRepository(session).add(q)
        repo = SqlAlchemyCommentRepository(session)
        for c in (c1, c2, foreign):
            await repo.add(c)
        await session.commit()

        listed = await repo.list_by_target(CommentTarget.QUESTION, q.id)
        assert [c.id for c in listed] == [c2.id, c1.id]  # 时间正序（1.3 功能域 9）
        assert listed[0].body.value == "评论正文"
        assert listed[0].author_id == author


async def test_answer_comments_grouped_by_answer() -> None:
    author = await _make_author()
    q = _question(author)
    a1 = _answer(q.id, author, at=_BASE)
    a2 = _answer(q.id, author, at=_BASE + timedelta(seconds=1))
    ac1 = _comment(CommentTarget.ANSWER, a1.id, author, at=_BASE + timedelta(seconds=2))
    async with session_factory() as session:
        await SqlAlchemyQuestionRepository(session).add(q)
        answers = SqlAlchemyAnswerRepository(session)
        await answers.add(a1)
        await answers.add(a2)
        comments = SqlAlchemyCommentRepository(session)
        await comments.add(ac1)
        await session.commit()

        on_a1 = await comments.list_by_target(CommentTarget.ANSWER, a1.id)
        on_a2 = await comments.list_by_target(CommentTarget.ANSWER, a2.id)
        assert [c.id for c in on_a1] == [ac1.id]
        assert on_a2 == []  # 答评不串挂


async def test_accept_writes_both_sides_and_rereads() -> None:
    """采纳双写跨会话回读：Answer.is_accepted + Question.accepted_answer_id 均落库。"""
    author = await _make_author()
    q = _question(author)
    a = _answer(q.id, author, at=_BASE)
    async with session_factory() as session:
        await SqlAlchemyQuestionRepository(session).add(q)
        await SqlAlchemyAnswerRepository(session).add(a)
        await session.commit()

    async with session_factory() as session:  # 新会话执行采纳（模拟一次请求）
        outcome = await AcceptAnswerUseCase(
            SqlAlchemyQuestionRepository(session), SqlAlchemyAnswerRepository(session)
        ).execute(AcceptAnswerCommand(answer_id=a.id, actor_id=author))
        await session.commit()
    assert outcome.event.answer_id == a.id

    async with session_factory() as session:  # 再新会话验证持久化
        reloaded_a = await SqlAlchemyAnswerRepository(session).get_by_id(a.id)
        reloaded_q = await SqlAlchemyQuestionRepository(session).get_by_id(q.id)
    assert reloaded_a is not None and reloaded_a.is_accepted is True
    assert reloaded_q is not None and reloaded_q.accepted_answer_id == a.id


async def test_accepted_answer_sorts_first_after_persistence() -> None:
    """采纳后 D2 排序：被采纳回答（净 0 票）置顶于高票未采纳（跨会话读时聚合）。"""
    author = await _make_author()
    q = _question(author)
    a_acc = _answer(q.id, author, at=_BASE)
    a_hi = _answer(q.id, author, at=_BASE + timedelta(seconds=1))
    async with session_factory() as session:
        await SqlAlchemyQuestionRepository(session).add(q)
        answers = SqlAlchemyAnswerRepository(session)
        await answers.add(a_acc)
        await answers.add(a_hi)
        await session.commit()
    async with session_factory() as session:
        await AcceptAnswerUseCase(
            SqlAlchemyQuestionRepository(session), SqlAlchemyAnswerRepository(session)
        ).execute(AcceptAnswerCommand(answer_id=a_acc.id, actor_id=author))
        await session.commit()

    async with session_factory() as session:
        ordered = await SqlAlchemyAnswerRepository(session).list_by_question(q.id)
    assert [x.id for x in ordered] == [a_acc.id, a_hi.id]
