"""标签目录集成测试：真 PostgreSQL。

覆盖：get-or-create 同名归并复用 id、大小写不敏感唯一（lower 索引）、
并发双插 savepoint 兜底（两 session 同名 → 同一 tag id）、问题打标回读、
孤儿标签保留（删问题不删目录行）。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.contexts.identity.application.commands import RegisterCommand
from app.contexts.identity.application.register_use_case import RegisterUseCase
from app.contexts.identity.infrastructure.password_hasher import BcryptPasswordHasher
from app.contexts.identity.infrastructure.repository import SqlAlchemyUserRepository
from app.contexts.qa.application.ask_question_use_case import AskQuestionUseCase
from app.contexts.qa.application.commands import AskQuestionCommand
from app.contexts.qa.domain.tag import Tag
from app.contexts.qa.infrastructure.models import QuestionModel, TagModel
from app.contexts.qa.infrastructure.repository import (
    SqlAlchemyQuestionRepository,
    SqlAlchemyTagCatalogRepository,
)
from app.shared.engine import session_factory

pytestmark = pytest.mark.integration


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


async def test_get_or_create_case_insensitive_reuses_row() -> None:
    """T02：先建 "SQL"，再取 "sql" → 同一行同一 id，目录不重复。"""
    name = f"t{uuid.uuid4().hex[:6]}"
    async with session_factory() as session:
        repo = SqlAlchemyTagCatalogRepository(session)
        first = await repo.get_or_create(Tag(name))
        second = await repo.get_or_create(Tag(name.upper()))
        assert first.id is not None
        assert second.id == first.id  # lower 键命中复用
        assert second.value == name  # 显示名 = 首见规范名
        await session.commit()


async def test_concurrent_get_or_create_converges_same_id() -> None:
    """并发双插同名标签：两独立事务各自 get_or_create → 撞唯一索引 savepoint 兜底，
    最终同一 tag id、tags 表仅一行。"""
    name = f"c{uuid.uuid4().hex[:6]}"

    async def worker() -> uuid.UUID:
        async with session_factory() as session:
            tag = await SqlAlchemyTagCatalogRepository(session).get_or_create(Tag(name))
            await session.commit()
            assert tag.id is not None
            return tag.id

    id_a, id_b = await asyncio.gather(worker(), worker())
    assert id_a == id_b
    async with session_factory() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(TagModel).where(
                    TagModel.key == name.lower()
                )
            )
        ).scalar_one()
        assert count == 1


async def test_nonascii_lower_divergence_key_single_source() -> None:
    """第九路 X-06 回归：İ（U+0130）Python lower 全映射 vs PG lower 简单映射——
    key 列单源后，"I" 与 "İ" 各自独立建行、互不冲突，也不触发 400 死路。"""
    async with session_factory() as session:
        repo = SqlAlchemyTagCatalogRepository(session)
        upper_i = await repo.get_or_create(Tag("I"))
        dotted = await repo.get_or_create(Tag("İ"))  # Python key = "i̇"（2 码位）
        assert upper_i.id is not None and dotted.id is not None
        assert upper_i.id != dotted.id  # 归并键不同 → 两行，无撞索引死路
        await session.commit()
        # 再取 İ 命中既有行（幂等）
        again = await SqlAlchemyTagCatalogRepository(session).get_or_create(Tag("İ"))
        assert again.id == dotted.id


async def test_question_with_tags_roundtrip() -> None:
    """打标提问 → 回读聚合带规范名与 id；目录同名标签被复用不新建。"""
    author_id = await _make_author()
    suffix = uuid.uuid4().hex[:6]
    t1, t2 = f"db{suffix}", f"sql{suffix}"
    async with session_factory() as session:
        use_case = AskQuestionUseCase(
            SqlAlchemyQuestionRepository(session), SqlAlchemyTagCatalogRepository(session)
        )
        question = await use_case.execute(
            AskQuestionCommand(
                title="标签回读", body="正文", author_id=author_id, tags=(t1, t2, t1.upper())
            )
        )
        await session.commit()
        assert len(question.tags) == 2  # 去重后 2 个
        assert {t.id for t in question.tags} == {question.tags[0].id, question.tags[1].id}

        fetched = await SqlAlchemyQuestionRepository(session).get_by_id(question.id)
        assert fetched is not None
        assert sorted(t.value for t in fetched.tags) == sorted([t1, t2])


async def test_orphan_tag_survives_question_delete() -> None:
    """v6：孤儿标签保留——直接删问题行，关联边 CASCADE 清除、目录行仍在。"""
    author_id = await _make_author()
    name = f"orph{uuid.uuid4().hex[:6]}"
    async with session_factory() as session:
        use_case = AskQuestionUseCase(
            SqlAlchemyQuestionRepository(session), SqlAlchemyTagCatalogRepository(session)
        )
        question = await use_case.execute(
            AskQuestionCommand(title="孤儿", body="正文", author_id=author_id, tags=(name,))
        )
        await session.commit()
        tag_id = question.tags[0].id

        await session.execute(
            QuestionModel.__table__.delete().where(QuestionModel.id == question.id)
        )
        await session.commit()

        assert await session.get(TagModel, tag_id) is not None  # 目录行保留
        from app.contexts.qa.infrastructure.models import QuestionTagModel

        links = (
            await session.execute(
                select(QuestionTagModel).where(QuestionTagModel.tag_id == tag_id)
            )
        ).scalars().all()
        assert links == []  # 边已 CASCADE
