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
from app.contexts.qa.domain.answer import Answer
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import QuestionSort
from app.contexts.qa.domain.value_objects import Body, Title


class FakeQuestionRepository:
    """内存仓储：按（created_at, id）倒序切片，模拟端口契约。"""

    def __init__(self) -> None:
        self.added: list[Question] = []

    async def add(self, question: Question) -> None:
        self.added.append(question)

    async def update(self, question: Question) -> None:
        return None

    async def get_by_id(self, question_id: UUID) -> Question | None:
        return next((q for q in self.added if q.id == question_id), None)

    async def list_paginated(
        self, page: int, page_size: int, sort: QuestionSort = QuestionSort.LATEST
    ) -> tuple[list[Question], int]:
        ordered = sorted(self.added, key=lambda q: (q.created_at, q.id), reverse=True)
        start = (page - 1) * page_size
        return ordered[start : start + page_size], len(self.added)


class FakeAnswerRepository:
    """内存回答仓储：list_by_question 按 D2 排序（已采纳最前 > 净票数降序 > 时间正序）。"""

    def __init__(self) -> None:
        self.added: list[Answer] = []

    async def add(self, answer: Answer) -> None:
        self.added.append(answer)

    async def update(self, answer: Answer) -> None:
        return None

    async def get_by_id(self, answer_id: UUID) -> Answer | None:
        return next((a for a in self.added if a.id == answer_id), None)

    async def list_by_question(self, question_id: UUID) -> list[Answer]:
        related = [a for a in self.added if a.question_id == question_id]
        return sorted(
            related,
            key=lambda a: (not a.is_accepted, -a.votes_count, a.created_at),
        )


class FakeCommentRepository:
    """内存评论仓储：list_by_target 按时间正序（1.3 功能域 9）。"""

    def __init__(self) -> None:
        self.added: list[Comment] = []

    async def add(self, comment: Comment) -> None:
        self.added.append(comment)

    async def list_by_target(
        self, target_type: CommentTarget, target_id: UUID
    ) -> list[Comment]:
        related = [
            c
            for c in self.added
            if c.target_type == target_type and c.target_id == target_id
        ]
        return sorted(related, key=lambda c: (c.created_at, c.id))


def _question(at: datetime) -> Question:
    return Question(
        id=uuid4(), title=Title("标题"), body=Body("正文"), author_id=uuid4(), created_at=at
    )


def _seed(count: int, start: datetime, step_seconds: int = 1) -> list[Question]:
    return [
        _question(start + timedelta(seconds=i * step_seconds)) for i in range(count)
    ]


def _answer(question_id: UUID, *, votes: int, accepted: bool, at: datetime) -> Answer:
    return Answer(
        id=uuid4(),
        question_id=question_id,
        author_id=uuid4(),
        body=Body("回答正文"),
        created_at=at,
        is_accepted=accepted,
        votes_count=votes,
    )


def _comment(target_type: CommentTarget, target_id: UUID, *, at: datetime) -> Comment:
    return Comment(
        id=uuid4(),
        target_type=target_type,
        target_id=target_id,
        author_id=uuid4(),
        body=Body("评论正文"),
        created_at=at,
    )


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


async def test_get_question_returns_detail_view_or_none() -> None:
    repo = FakeQuestionRepository()
    answers = FakeAnswerRepository()
    comments = FakeCommentRepository()
    question = _question(datetime(2026, 1, 1, tzinfo=UTC))
    repo.added = [question]
    use_case = GetQuestionUseCase(repo, answers, comments)

    found = await use_case.execute(GetQuestionQuery(question_id=question.id))
    assert found is not None
    assert found.question is question
    assert found.answers == []  # 无回答时为空列表（非 None）
    assert found.question_comments == []
    assert found.answer_comments == {}

    assert await use_case.execute(GetQuestionQuery(question_id=uuid4())) is None


async def test_detail_groups_question_and_answer_comments() -> None:
    """题评挂顶层、答评按 answer_id 分组（1.3 功能域 9 读取路径）。"""
    repo = FakeQuestionRepository()
    answers = FakeAnswerRepository()
    comments = FakeCommentRepository()
    question = _question(datetime(2026, 1, 1, tzinfo=UTC))
    repo.added = [question]
    a1 = _answer(question.id, votes=0, accepted=False, at=datetime(2026, 1, 2, tzinfo=UTC))
    answers.added = [a1]
    comments.added = [
        _comment(CommentTarget.QUESTION, question.id, at=datetime(2026, 1, 3, tzinfo=UTC)),
        _comment(CommentTarget.ANSWER, a1.id, at=datetime(2026, 1, 4, tzinfo=UTC)),
    ]

    view = await GetQuestionUseCase(repo, answers, comments).execute(
        GetQuestionQuery(question_id=question.id)
    )
    assert view is not None
    assert [c.id for c in view.question_comments] == [comments.added[0].id]
    assert [c.id for c in view.answer_comments[str(a1.id)]] == [comments.added[1].id]


async def test_detail_answers_ordered_by_d2() -> None:
    """D2 定稿 + v3 裁定 #1：已采纳恒最前 > 净票数降序 > 时间正序。"""
    repo = FakeQuestionRepository()
    answers = FakeAnswerRepository()
    comments = FakeCommentRepository()
    question = _question(datetime(2026, 1, 1, tzinfo=UTC))
    repo.added = [question]

    base = datetime(2026, 1, 2, tzinfo=UTC)
    answers.added = [
        _answer(question.id, votes=1, accepted=False, at=base),
        _answer(question.id, votes=5, accepted=False, at=base + timedelta(seconds=1)),
        _answer(question.id, votes=1, accepted=True, at=base + timedelta(seconds=2)),
        _answer(question.id, votes=-2, accepted=False, at=base + timedelta(seconds=3)),
    ]

    view = await GetQuestionUseCase(repo, answers, comments).execute(
        GetQuestionQuery(question_id=question.id)
    )
    assert view is not None
    ordered = view.answers
    # 采纳票（votes=1）恒最前，压过高票未采纳（votes=5）——1.3 功能域 8 场景
    assert ordered[0].is_accepted is True
    assert [a.votes_count for a in ordered] == [1, 5, 1, -2]
