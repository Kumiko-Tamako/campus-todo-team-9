"""ListQuestions/GetQuestion 用例单元测试：fake 仓储，不连库（进 CI）。

排序与切片是仓储实现的 SQL 行为，不在本层验证（集成层覆盖）；
本层验证用例对分页元数据的组装：total_pages 进位与空库契约。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.contexts.qa.application.get_question_use_case import GetQuestionUseCase
from app.contexts.qa.application.list_questions_use_case import ListQuestionsUseCase
from app.contexts.qa.application.queries import GetQuestionQuery, ListQuestionsQuery
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.value_objects import Body, Title


class FakeQuestionRepository:
    """内存仓储：按（created_at, id）倒序切片，模拟端口契约。"""

    def __init__(self) -> None:
        self.added: list[Question] = []

    async def add(self, question: Question) -> None:
        self.added.append(question)

    async def get_by_id(self, question_id: UUID) -> Question | None:
        return next((q for q in self.added if q.id == question_id), None)

    async def list_paginated(self, page: int, page_size: int) -> tuple[list[Question], int]:
        ordered = sorted(self.added, key=lambda q: (q.created_at, q.id), reverse=True)
        start = (page - 1) * page_size
        return ordered[start : start + page_size], len(self.added)


def _question(at: datetime) -> Question:
    return Question(
        id=uuid4(), title=Title("标题"), body=Body("正文"), author_id=uuid4(), created_at=at
    )


def _seed(count: int, start: datetime, step_seconds: int = 1) -> list[Question]:
    return [
        _question(start + timedelta(seconds=i * step_seconds)) for i in range(count)
    ]


async def test_list_assembles_page_metadata() -> None:
    repo = FakeQuestionRepository()
    repo.added = _seed(25, datetime(2026, 1, 1, tzinfo=UTC))
    result = await ListQuestionsUseCase(repo).execute(ListQuestionsQuery(page=1, page_size=20))
    assert len(result.items) == 20
    assert result.total == 25
    assert result.page == 1
    assert result.page_size == 20
    assert result.total_pages == 2  # ceil(25/20)


async def test_total_pages_always_ceils_up() -> None:
    repo = FakeQuestionRepository()
    for total, expected in ((21, 2), (40, 2), (1, 1), (20, 1)):
        repo.added = _seed(total, datetime(2026, 1, 1, tzinfo=UTC))
        result = await ListQuestionsUseCase(repo).execute(
            ListQuestionsQuery(page=1, page_size=20)
        )
        assert result.total_pages == expected, f"total={total}"


async def test_total_pages_zero_when_empty() -> None:
    repo = FakeQuestionRepository()
    result = await ListQuestionsUseCase(repo).execute(ListQuestionsQuery(page=1, page_size=20))
    assert result.items == []
    assert result.total == 0
    assert result.total_pages == 0  # 空库契约（2.8 openapi）


async def test_get_question_returns_aggregate_or_none() -> None:
    repo = FakeQuestionRepository()
    question = _question(datetime(2026, 1, 1, tzinfo=UTC))
    repo.added = [question]
    use_case = GetQuestionUseCase(repo)
    found = await use_case.execute(GetQuestionQuery(question_id=question.id))
    assert found is question
    assert await use_case.execute(GetQuestionQuery(question_id=uuid4())) is None
