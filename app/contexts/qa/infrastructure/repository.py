from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.value_objects import Body, Title
from app.contexts.qa.infrastructure.models import QuestionModel


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
            )
        )
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
        )

    async def list_paginated(self, page: int, page_size: int) -> tuple[list[Question], int]:
        # 总条数与当前页同一事务快照，保证分页元数据一致
        total = (
            await self._session.execute(select(func.count()).select_from(QuestionModel))
        ).scalar_one()
        stmt = (
            select(QuestionModel)
            # created_at 同微秒并发发帖（Q-12 连发 50 帖场景）顺序不定，
            # id 作 tiebreaker 保证确定性全序，跨页不重复/不漏项
            .order_by(QuestionModel.created_at.desc(), QuestionModel.id.desc())
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
                )
                for model in models
            ],
            total,
        )
