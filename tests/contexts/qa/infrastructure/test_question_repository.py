"""QuestionRepository 集成测试：真 PostgreSQL（docker compose up -d）。

questions.author_id 外键指向 users，故先经注册用例建作者。
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
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.value_objects import Body, Title
from app.contexts.qa.infrastructure.repository import SqlAlchemyQuestionRepository
from app.shared.engine import session_factory

pytestmark = pytest.mark.integration


async def _make_author() -> uuid.UUID:
    """注册一个学生用户并 commit，返回其 user.id（供 question.author_id 外键）。"""
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


async def test_question_persists_and_roundtrips() -> None:
    author_id = await _make_author()
    async with session_factory() as session:
        use_case = AskQuestionUseCase(SqlAlchemyQuestionRepository(session))
        question = await use_case.execute(
            AskQuestionCommand(
                title="  仓储回读测试标题  ",
                body="仓储回读测试正文",
                author_id=author_id,
            )
        )
        await session.commit()

        repo = SqlAlchemyQuestionRepository(session)
        fetched = await repo.get_by_id(question.id)
        assert fetched is not None
        assert fetched.id == question.id
        assert fetched.title.value == "仓储回读测试标题"  # 落库即规范化后形态
        assert fetched.body.value == "仓储回读测试正文"
        assert fetched.author_id == author_id
        assert fetched.created_at.tzinfo is not None


async def test_get_by_id_missing_returns_none() -> None:
    async with session_factory() as session:
        repo = SqlAlchemyQuestionRepository(session)
        assert await repo.get_by_id(uuid.uuid4()) is None


async def test_list_paginated_orders_and_slices_exactly() -> None:
    """全表 (created_at, id) 严格降序（确定性全序）+ offset/limit 与全量读取一致。

    种子用过去时间戳（不霸占列表头部，毒化其他测试的"最新"断言）；
    断言对表中既有数据零假设（容忍 page_size 窗口外数据）。
    """
    author_id = await _make_author()
    base = datetime(2020, 1, 1, tzinfo=UTC)
    seeds = [
        Question(
            id=uuid.uuid4(),
            title=Title(f"排序切片 {i}"),
            body=Body("正文"),
            author_id=author_id,
            created_at=base + timedelta(seconds=i),
        )
        for i in range(5)
    ]
    async with session_factory() as session:
        repo = SqlAlchemyQuestionRepository(session)
        for seed in seeds:
            await repo.add(seed)
        await session.commit()

        full_items, total = await repo.list_paginated(page=1, page_size=1000)
        assert total >= 5
        keys = [(q.created_at, q.id) for q in full_items]
        assert keys == sorted(keys, reverse=True)  # 全表降序无歧义

        # 在窗口内的种子呈新→旧相对序（种子时间戳最旧，通常整段在窗口末尾）
        seed_ids = {s.id for s in seeds}
        present = [q.id for q in full_items if q.id in seed_ids]
        expected_order = [s.id for s in reversed(seeds)]
        assert present == [i for i in expected_order if i in set(present)]

        # offset/limit 切片必须与同一全序的窗口完全一致
        page2_items, _ = await repo.list_paginated(page=2, page_size=3)
        assert [q.id for q in page2_items] == [q.id for q in full_items[3:6]]
        page3_items, _ = await repo.list_paginated(page=3, page_size=3)
        assert [q.id for q in page3_items] == [q.id for q in full_items[6:9]]


async def test_list_paginated_tiebreaker_deterministic() -> None:
    """同微秒并发发帖（Q-12 连发场景）created_at 相同：按 id DESC 确定性定序。"""
    author_id = await _make_author()
    same_at = datetime(2019, 6, 1, tzinfo=UTC)
    qa = Question(
        id=uuid.uuid4(), title=Title("同刻甲"), body=Body("正文"),
        author_id=author_id, created_at=same_at,
    )
    qb = Question(
        id=uuid.uuid4(), title=Title("同刻乙"), body=Body("正文"),
        author_id=author_id, created_at=same_at,
    )
    async with session_factory() as session:
        repo = SqlAlchemyQuestionRepository(session)
        await repo.add(qa)
        await repo.add(qb)
        await session.commit()

        items, _total = await repo.list_paginated(page=1, page_size=1000)
        ids = [q.id for q in items]
        ia, ib = ids.index(qa.id), ids.index(qb.id)
        # 同 created_at：id 大者在前（确定性全序，跨页不重复/不漏项）
        assert (ia < ib) == (qa.id > qb.id)
