"""AnswerRepository / VoteRepository 集成测试：真 PostgreSQL（docker compose up -d）。

覆盖：落库回读、净票数聚合（v3 裁定 #1：up − down）、D2 排序（采纳置顶 > 净票降序 >
时间正序 > id tiebreaker）、一人一票事前查询与复合唯一索引并发兜底（v3 裁定 #5）。
种子用过去时间戳，不毒化其他测试的"最新"断言。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.contexts.identity.application.commands import RegisterCommand
from app.contexts.identity.application.register_use_case import RegisterUseCase
from app.contexts.identity.infrastructure.password_hasher import BcryptPasswordHasher
from app.contexts.identity.infrastructure.repository import SqlAlchemyUserRepository
from app.contexts.qa.application.ask_question_use_case import AskQuestionUseCase
from app.contexts.qa.application.commands import AskQuestionCommand
from app.contexts.qa.domain.answer import Answer
from app.contexts.qa.domain.errors import AlreadyVotedError
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.value_objects import Body
from app.contexts.qa.domain.vote import Vote, VoteDirection, VoteTarget
from app.contexts.qa.infrastructure.repository import (
    SqlAlchemyAnswerRepository,
    SqlAlchemyQuestionRepository,
    SqlAlchemyVoteRepository,
)
from app.shared.engine import session_factory

pytestmark = pytest.mark.integration

_BASE = datetime(2018, 1, 1, tzinfo=UTC)  # 足够旧：不进入任何"最新"断言窗口


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


async def _make_question(author_id: uuid.UUID) -> Question:
    async with session_factory() as session:
        question = await AskQuestionUseCase(SqlAlchemyQuestionRepository(session)).execute(
            AskQuestionCommand(
                title=f"答票仓储 {uuid.uuid4().hex[:8]}",
                body="正文",
                author_id=author_id,
            )
        )
        await session.commit()
        return question


def _answer(question_id: uuid.UUID, author_id: uuid.UUID, *, at: datetime) -> Answer:
    return Answer(
        id=uuid.uuid4(),
        question_id=question_id,
        author_id=author_id,
        body=Body("回答正文"),
        created_at=at,
    )


async def test_answer_persists_and_roundtrips() -> None:
    author = await _make_author()
    question = await _make_question(author)
    answer = _answer(question.id, author, at=_BASE)
    async with session_factory() as session:
        await SqlAlchemyAnswerRepository(session).add(answer)
        await session.commit()

        fetched = await SqlAlchemyAnswerRepository(session).get_by_id(answer.id)
        assert fetched is not None
        assert fetched.id == answer.id
        assert fetched.question_id == question.id
        assert fetched.author_id == author
        assert fetched.body.value == "回答正文"
        assert fetched.is_accepted is False
        assert fetched.votes_count == 0  # 无票净分为 0


async def test_net_votes_up_minus_down() -> None:
    """v3 裁定 #1：净票数 = up − down，可为负。"""
    author = await _make_author()
    voter1, voter2, voter3 = await _make_author(), await _make_author(), await _make_author()
    question = await _make_question(author)
    answer = _answer(question.id, author, at=_BASE)
    async with session_factory() as session:
        await SqlAlchemyAnswerRepository(session).add(answer)
        votes = SqlAlchemyVoteRepository(session)
        for voter, direction in (
            (voter1, VoteDirection.UP),
            (voter2, VoteDirection.UP),
            (voter3, VoteDirection.DOWN),
        ):
            await votes.add(
                Vote.cast(
                    user_id=voter,
                    target_type=VoteTarget.ANSWER,
                    target_id=answer.id,
                    direction=direction,
                )
            )
        await session.commit()

        fetched = await SqlAlchemyAnswerRepository(session).get_by_id(answer.id)
        assert fetched is not None
        assert fetched.votes_count == 1  # 2 up − 1 down


async def test_list_by_question_orders_d2_with_net_votes() -> None:
    """D2：已采纳恒最前 > 净票数降序 > 时间正序 > id tiebreaker。"""
    author = await _make_author()
    question = await _make_question(author)
    a_low = _answer(question.id, author, at=_BASE + timedelta(seconds=1))
    a_high = _answer(question.id, author, at=_BASE + timedelta(seconds=2))
    a_accepted = _answer(question.id, author, at=_BASE + timedelta(seconds=3))
    a_negative = _answer(question.id, author, at=_BASE + timedelta(seconds=4))
    other_question = await _make_question(author)
    foreign = _answer(other_question.id, author, at=_BASE)  # 属于另一问题，不得混入

    voters = [await _make_author() for _ in range(6)]
    async with session_factory() as session:
        answers = SqlAlchemyAnswerRepository(session)
        for a in (a_low, a_high, a_accepted, a_negative, foreign):
            await answers.add(a)
        votes = SqlAlchemyVoteRepository(session)
        plan = [
            (a_high, 3 * [VoteDirection.UP]),  # 净 +3
            (a_low, [VoteDirection.UP]),  # 净 +1
            (a_negative, [VoteDirection.DOWN, VoteDirection.DOWN]),  # 净 −2
        ]
        cursor = 0
        for target, directions in plan:
            for d in directions:
                await votes.add(
                    Vote.cast(
                        user_id=voters[cursor],
                        target_type=VoteTarget.ANSWER,
                        target_id=target.id,
                        direction=d,
                    )
                )
                cursor += 1
        await session.commit()

        ordered = await answers.list_by_question(question.id)
        # a_accepted 未采纳净 0 票：按净票降序落在 +1 与 −2 之间
        assert [a.id for a in ordered] == [a_high.id, a_low.id, a_accepted.id, a_negative.id]
        assert [a.votes_count for a in ordered] == [3, 1, 0, -2]
        assert foreign.id not in [a.id for a in ordered]


async def test_accepted_answer_sorts_first_regardless_of_votes() -> None:
    """1.3 功能域 8：被采纳回答（净 0 票）优先于高票未采纳回答（净 5 票）。

    is_accepted 列先行落库（分支 2 才提供 accept() 行为），此处直接构造验证排序。
    """
    author = await _make_author()
    question = await _make_question(author)
    a_accepted = _answer(question.id, author, at=_BASE)
    a_accepted.is_accepted = True
    a_high = _answer(question.id, author, at=_BASE + timedelta(seconds=1))
    voters = [await _make_author() for _ in range(5)]
    async with session_factory() as session:
        await SqlAlchemyAnswerRepository(session).add(a_accepted)
        await SqlAlchemyAnswerRepository(session).add(a_high)
        votes = SqlAlchemyVoteRepository(session)
        for voter in voters:
            await votes.add(
                Vote.cast(
                    user_id=voter,
                    target_type=VoteTarget.ANSWER,
                    target_id=a_high.id,
                    direction=VoteDirection.UP,
                )
            )
        await session.commit()

        ordered = await SqlAlchemyAnswerRepository(session).list_by_question(question.id)
        assert [a.id for a in ordered] == [a_accepted.id, a_high.id]


async def test_find_by_user_target_roundtrip_and_miss() -> None:
    author = await _make_author()
    voter = await _make_author()
    question = await _make_question(author)
    vote = Vote.cast(
        user_id=voter,
        target_type=VoteTarget.QUESTION,
        target_id=question.id,
        direction=VoteDirection.UP,
    )
    async with session_factory() as session:
        await SqlAlchemyVoteRepository(session).add(vote)
        await session.commit()

        repo = SqlAlchemyVoteRepository(session)
        found = await repo.find_by_user_target(voter, VoteTarget.QUESTION, question.id)
        assert found is not None
        assert found.id == vote.id
        assert found.direction is VoteDirection.UP
        # 换目标类型/换用户均查不到（复合唯一按三元组）
        assert await repo.find_by_user_target(voter, VoteTarget.ANSWER, question.id) is None
        assert await repo.find_by_user_target(author, VoteTarget.QUESTION, question.id) is None


async def test_duplicate_vote_same_user_target_rejected_by_unique_index() -> None:
    """一人一票库级兜底：绕过事前检查直接 add 第二票 → AlreadyVotedError。"""
    author = await _make_author()
    voter = await _make_author()
    question = await _make_question(author)
    async with session_factory() as session:
        votes = SqlAlchemyVoteRepository(session)
        await votes.add(
            Vote.cast(
                user_id=voter,
                target_type=VoteTarget.QUESTION,
                target_id=question.id,
                direction=VoteDirection.UP,
            )
        )
        await session.flush()
        with pytest.raises(AlreadyVotedError):
            await votes.add(
                Vote.cast(  # 换方向同样被拒（v3 裁定 #5：不可改票，索引不分方向）
                    user_id=voter,
                    target_type=VoteTarget.QUESTION,
                    target_id=question.id,
                    direction=VoteDirection.DOWN,
                )
            )
        await session.rollback()
