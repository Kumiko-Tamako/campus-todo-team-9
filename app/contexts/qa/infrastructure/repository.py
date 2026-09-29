from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, CursorResult, case, func, select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.qa.domain.answer import Answer
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.errors import (
    AlreadyVotedError,
    AnswerAlreadyAcceptedError,
    QuestionAlreadyClosedError,
    QuestionClosedError,
)
from app.contexts.qa.domain.question import Question, QuestionStatus
from app.contexts.qa.domain.repository import QuestionSort
from app.contexts.qa.domain.tag import Tag
from app.contexts.qa.domain.value_objects import Body, Title
from app.contexts.qa.domain.vote import Vote, VoteDirection, VoteTarget
from app.contexts.qa.infrastructure.models import (
    AnswerModel,
    CommentModel,
    QuestionModel,
    QuestionTagModel,
    TagModel,
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
                status=question.status.value,
            )
        )
        await self._session.flush()
        # 打标关联（迭代 4）：tag 行已由目录 get-or-create 落库，此处只挂多对多边
        for tag in question.tags:
            if tag.id is not None:
                self._session.add(QuestionTagModel(question_id=question.id, tag_id=tag.id))
        await self._session.flush()

    async def update(self, question: Question) -> None:
        """可变态条件更新（迭代 5 起并发安全，参照采纳条件 UPDATE 先例）：

        - 关闭动作（实体 status=closed）：`WHERE status<>'closed' AND accepted_answer_id IS NULL`
          ——并发重复关闭恰一路 204；并发"先采纳后关闭"竞态被库级挡下（不变式 5 兜底）
        - 编辑/采纳动作（实体 status=open）：`WHERE status<>'closed'`
          ——关闭提交后仍到达的写入转 409（全冻结库级兜底，防状态回退/越权写入）
        rowcount=0 时读最新行转译领域异常（409 语义），不泄露内部细节。
        """
        values: dict[str, Any]
        conditions: list[ColumnElement[bool]] = [
            QuestionModel.status != QuestionStatus.CLOSED.value
        ]
        if question.status is QuestionStatus.CLOSED:
            # 关闭动作只写状态列：不触碰 title/body/accepted，减少与在途编辑/采纳
            # 已提交写入互相覆盖的丢失更新面；并加"未采纳"库级守卫（不变式 5）
            values = {"status": QuestionStatus.CLOSED.value}
            conditions.append(QuestionModel.accepted_answer_id.is_(None))
        else:
            # 编辑/采纳动作（status=open）：同步内容与采纳引用；已关闭行被 WHERE 挡下
            values = {
                "title": question.title.value,
                "body": question.body.value,
                "accepted_answer_id": question.accepted_answer_id,
            }
        stmt = (
            sql_update(QuestionModel)
            .where(QuestionModel.id == question.id, *conditions)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        if result.rowcount > 0:
            return
        latest = (
            await self._session.execute(
                select(QuestionModel.status, QuestionModel.accepted_answer_id).where(
                    QuestionModel.id == question.id
                )
            )
        ).first()
        accepted = latest[1] if latest is not None else None
        if question.status is QuestionStatus.CLOSED:
            if accepted is not None:
                raise AnswerAlreadyAcceptedError("该问题已有采纳答案，不可关闭（并发兜底）")
            raise QuestionAlreadyClosedError("问题已关闭（并发兜底）")
        # open 意图写入撞上已关闭行（编辑/采纳与关闭竞态）
        raise QuestionClosedError("已关闭的问题不可更新（并发兜底）")

    async def _tags_for(self, question_ids: list[UUID]) -> dict[UUID, list[Tag]]:
        """批量装配问题标签（列表/详情共用；一次 JOIN 防 N+1）。

        显示序 = 规范码点序（Python 排序，locale 无关；PG collation 与码点序
        对中文可能分歧，故不在 SQL 侧 order_by name——与 ListTagsUseCase 同口径）。
        """
        if not question_ids:
            return {}
        stmt = (
            select(QuestionTagModel.question_id, TagModel.id, TagModel.name)
            .join(TagModel, TagModel.id == QuestionTagModel.tag_id)
            .where(QuestionTagModel.question_id.in_(question_ids))
        )
        result: dict[UUID, list[Tag]] = {qid: [] for qid in question_ids}
        for qid, tag_id, name in (await self._session.execute(stmt)).all():
            result[qid].append(Tag(value=name, id=tag_id))
        for tags in result.values():
            tags.sort(key=lambda t: t.value)
        return result

    async def get_by_id(self, question_id: UUID) -> Question | None:
        stmt = select(QuestionModel).where(QuestionModel.id == question_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        # 重建聚合：历史事件不从库回放（与 identity _to_domain 同模式）
        tags_map = await self._tags_for([question_id])
        return Question(
            id=model.id,
            title=Title(model.title),
            body=Body(model.body),
            author_id=model.author_id,
            created_at=model.created_at,
            accepted_answer_id=model.accepted_answer_id,
            status=QuestionStatus(model.status),
            tags=tags_map[question_id],
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
        tags_map = await self._tags_for([model.id for model in models])
        return (
            [
                Question(
                    id=model.id,
                    title=Title(model.title),
                    body=Body(model.body),
                    author_id=model.author_id,
                    created_at=model.created_at,
                    accepted_answer_id=model.accepted_answer_id,
                    status=QuestionStatus(model.status),
                    tags=tags_map[model.id],
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


class SqlAlchemyTagCatalogRepository:
    """TagCatalogRepository 端口的 SQLAlchemy 实现（迭代 4，US-T01/T02）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _find(self, key: str) -> TagModel | None:
        stmt = select(TagModel).where(TagModel.key == key)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_or_create(self, tag: Tag) -> Tag:
        # 随用随建（T02）：先按归并键查既有行（key 列唯一索引）
        model = await self._find(tag.key)
        if model is not None:
            return Tag(value=model.name, id=model.id)
        try:
            # savepoint 隔离插入：并发双插撞唯一索引时仅回滚本 savepoint，
            # 外层事务（含同请求已写的其它标签行）不受影响
            async with self._session.begin_nested():
                row = TagModel(id=uuid4(), name=tag.value, key=tag.key)
                self._session.add(row)
                await self._session.flush()
        except IntegrityError:
            # 竞败方：他事务已建同键行 → 重查复用（幂等，不报错）。
            # 键由应用单侧计算（key 列），与库判定恒等，重查必命中
            model = await self._find(tag.key)
            if model is None:  # 理论不可达（撞唯一索引必有行）；防御性上抛
                raise
            return Tag(value=model.name, id=model.id)
        return Tag(value=tag.value, id=row.id)

    async def list_all(self) -> list[Tag]:
        models = (
            (await self._session.execute(select(TagModel).order_by(TagModel.name)))
            .scalars()
            .all()
        )
        return [Tag(value=m.name, id=m.id) for m in models]
