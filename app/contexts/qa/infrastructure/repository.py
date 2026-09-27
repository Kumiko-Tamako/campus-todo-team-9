from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import ColumnElement, CursorResult, case, func, select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.qa.domain.answer import Answer
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.errors import (
    AlreadyVotedError,
    AnswerAlreadyAcceptedError,
)
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import QuestionSort
from app.contexts.qa.domain.value_objects import Body, Title
from app.contexts.qa.domain.vote import Vote, VoteDirection, VoteTarget
from app.contexts.qa.infrastructure.models import (
    AnswerModel,
    CommentModel,
    QuestionModel,
    VoteModel,
)


def _net_votes_expr() -> ColumnElement[int]:
    """净票数表达式（v3 裁定 #1：up − down）：赞成 +1、反对 −1 求和，无票为 0。"""
    return func.coalesce(
        func.sum(case((VoteModel.direction == VoteDirection.UP.value, 1), else_=-1)),
        0,
    )


def _question_net_votes() -> ColumnElement[int]:
    """问题净票数相关子查询（列表 votes 排序用，v3 裁定 #4）。"""
    return (
        select(_net_votes_expr())
        .where(
            VoteModel.target_type == VoteTarget.QUESTION.value,
            VoteModel.target_id == QuestionModel.id,
        )
        .correlate(QuestionModel)
        .scalar_subquery()
    )


class SqlAlchemyQuestionRepository:
    """QuestionRepository 端口的 SQLAlchemy 实现。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, question: Question) -> None:
        self._session.add(
            QuestionModel(
                id=question.id,
                title=question.title.value,
                body=question.body.value,
                author_id=question.author_id,
                created_at=question.created_at,
                accepted_answer_id=question.accepted_answer_id,
            )
        )
        await self._session.flush()

    async def update(self, question: Question) -> None:
        # 采纳双写（US-V03）：只同步可变态 accepted_answer_id，其余字段建后不改（编辑属 Q08）
        model = await self._session.get(QuestionModel, question.id)
        if model is None:  # 理论不可达（用例先 get_by_id），防御性保持端口幂等语义
            return
        model.accepted_answer_id = question.accepted_answer_id
        await self._session.flush()

    async def get_by_id(self, question_id: UUID) -> Question | None:
        stmt = select(QuestionModel).where(QuestionModel.id == question_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        # 重建聚合：历史事件不从库回放（与 identity _to_domain 同模式）
        return Question(
            id=model.id,
            title=Title(model.title),
            body=Body(model.body),
            author_id=model.author_id,
            created_at=model.created_at,
            accepted_answer_id=model.accepted_answer_id,
        )

    async def list_paginated(
        self, page: int, page_size: int, sort: QuestionSort = QuestionSort.LATEST
    ) -> tuple[list[Question], int]:
        # 总条数与当前页同一事务快照，保证分页元数据一致
        total = (
            await self._session.execute(select(func.count()).select_from(QuestionModel))
        ).scalar_one()
        if sort is QuestionSort.VOTES:
            # v3 裁定 #4：净票数高→低；created_at/id 作确定性 tiebreaker 保证跨页稳定
            net = _question_net_votes()
            order_by: tuple[ColumnElement[Any], ...] = (
                net.desc(),
                QuestionModel.created_at.desc(),
                QuestionModel.id.desc(),
            )
        else:
            # created_at 同微秒并发发帖（Q-12 连发 50 帖场景）顺序不定，
            # id 作 tiebreaker 保证确定性全序，跨页不重复/不漏项
            order_by = (QuestionModel.created_at.desc(), QuestionModel.id.desc())
        stmt = (
            select(QuestionModel)
            .order_by(*order_by)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return (
            [
                Question(
                    id=model.id,
                    title=Title(model.title),
                    body=Body(model.body),
                    author_id=model.author_id,
                    created_at=model.created_at,
                    accepted_answer_id=model.accepted_answer_id,
                )
                for model in models
            ],
            total,
        )


class SqlAlchemyAnswerRepository:
    """AnswerRepository 端口的 SQLAlchemy 实现。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, answer: Answer) -> None:
        self._session.add(
            AnswerModel(
                id=answer.id,
                body=answer.body.value,
                question_id=answer.question_id,
                author_id=answer.author_id,
                is_accepted=answer.is_accepted,
                created_at=answer.created_at,
            )
        )
        await self._session.flush()

    async def update(self, answer: Answer) -> None:
        # 采纳翻转（US-V03）：只同步可变态 is_accepted。
        # 并发兜底双保险：① 部分唯一索引 uq_answers_one_accepted_per_question 防"同题多答案"
        # （AC-12）；② 下方条件 UPDATE（WHERE is_accepted=false + rowcount）防"同一 answer 行
        # 重复翻转"——第五路 K-03：应用层先读后写在并发下可多路过检查；条件更新下 PG 行锁
        # 等待后按最新版本重判 WHERE，仅 1 路 rowcount=1，其余归 409。
        model = await self._session.get(AnswerModel, answer.id)
        if model is None:  # 理论不可达（用例先 get_by_id），防御性
            return
        stmt = (
            sql_update(AnswerModel)
            .where(AnswerModel.id == answer.id, AnswerModel.is_accepted.is_(False))
            .values(is_accepted=True)
            .execution_options(synchronize_session=False)
        )
        try:
            result = cast(CursorResult[Any], await self._session.execute(stmt))
        except IntegrityError as exc:
            # 同题【不同】答案并发抢采：部分唯一索引在首个事务提交后令后到者的索引
            # 插入失败（AC-12 库级兜底，289a001 条件 UPDATE 重写时曾遗漏本翻译致 400）。
            raise AnswerAlreadyAcceptedError("该问题已有采纳答案（并发兜底）") from exc
        if result.rowcount == 0:
            raise AnswerAlreadyAcceptedError("该答案已被采纳")

    async def get_by_id(self, answer_id: UUID) -> Answer | None:
        model = (
            await self._session.execute(
                select(AnswerModel).where(AnswerModel.id == answer_id)
            )
        ).scalar_one_or_none()
        if model is None:
            return None
        return Answer(
            id=model.id,
            question_id=model.question_id,
            author_id=model.author_id,
            body=Body(model.body),
            created_at=model.created_at,
            is_accepted=model.is_accepted,
            votes_count=await self._net_votes(VoteTarget.ANSWER, model.id),
        )

    async def _net_votes(self, target_type: VoteTarget, target_id: UUID) -> int:
        stmt = (
            select(_net_votes_expr())
            .select_from(VoteModel)
            .where(
                VoteModel.target_type == target_type.value,
                VoteModel.target_id == target_id,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_by_question(self, question_id: UUID) -> list[Answer]:
        # D2 排序（净票口径 v3 #1）：已采纳恒最前 > 净票数降序 > 时间正序 > id tiebreaker。
        # 每答净票用相关子查询聚合，避免 JOIN 折叠行数。
        net = (
            select(_net_votes_expr())
            .where(
                VoteModel.target_type == VoteTarget.ANSWER.value,
                VoteModel.target_id == AnswerModel.id,
            )
            .correlate(AnswerModel)
            .scalar_subquery()
        )
        stmt = (
            select(AnswerModel, net.label("net_votes"))
            .where(AnswerModel.question_id == question_id)
            .order_by(
                AnswerModel.is_accepted.desc(),
                net.desc(),
                AnswerModel.created_at.asc(),
                AnswerModel.id.asc(),
            )
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            Answer(
                id=model.id,
                question_id=model.question_id,
                author_id=model.author_id,
                body=Body(model.body),
                created_at=model.created_at,
                is_accepted=model.is_accepted,
                votes_count=int(net_votes),
            )
            for model, net_votes in rows
        ]


class SqlAlchemyVoteRepository:
    """VoteRepository 端口的 SQLAlchemy 实现。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_user_target(
        self, user_id: UUID, target_type: VoteTarget, target_id: UUID
    ) -> Vote | None:
        model = (
            await self._session.execute(
                select(VoteModel).where(
                    VoteModel.user_id == user_id,
                    VoteModel.target_type == target_type.value,
                    VoteModel.target_id == target_id,
                )
            )
        ).scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def add(self, vote: Vote) -> None:
        self._session.add(
            VoteModel(
                id=vote.id,
                user_id=vote.user_id,
                target_type=vote.target_type.value,
                target_id=vote.target_id,
                direction=vote.direction.value,
                created_at=vote.created_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # 并发窗口内重复票：复合唯一索引兜底 → 重复票语义（与 identity 注册并发兜底同模式）。
            # 不回显 exc.orig（含约束名/DB 细节，Bug-5 泄露）——详情随异常链入服务端日志
            raise AlreadyVotedError("已对该对象投过票（并发兜底）") from exc

    @staticmethod
    def _to_domain(model: VoteModel) -> Vote:
        return Vote(
            id=model.id,
            user_id=model.user_id,
            target_type=VoteTarget(model.target_type),
            target_id=model.target_id,
            direction=VoteDirection(model.direction),
            created_at=model.created_at,
        )


class SqlAlchemyCommentRepository:
    """CommentRepository 端口的 SQLAlchemy 实现（迭代 3，US-C01）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, comment: Comment) -> None:
        self._session.add(
            CommentModel(
                id=comment.id,
                body=comment.body.value,
                target_type=comment.target_type.value,
                target_id=comment.target_id,
                author_id=comment.author_id,
                created_at=comment.created_at,
            )
        )
        await self._session.flush()

    async def list_by_target(
        self, target_type: CommentTarget, target_id: UUID
    ) -> list[Comment]:
        stmt = (
            select(CommentModel)
            .where(
                CommentModel.target_type == target_type.value,
                CommentModel.target_id == target_id,
            )
            # 1.3 功能域 9：评论按时间正序；created_at 同刻以 id tiebreaker 定确定性全序
            .order_by(CommentModel.created_at.asc(), CommentModel.id.asc())
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [
            Comment(
                id=model.id,
                target_type=CommentTarget(model.target_type),
                target_id=model.target_id,
                author_id=model.author_id,
                body=Body(model.body),
                created_at=model.created_at,
            )
            for model in models
        ]
