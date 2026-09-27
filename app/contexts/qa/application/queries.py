"""列表/详情用例的输入查询（只读，与 commands.py 的写命令对位）。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.contexts.qa.domain.repository import QuestionSort


@dataclass(frozen=True, slots=True)
class ListQuestionsQuery:
    """列表查询参数（ge/le 边界与 sort 枚举校验由路由层 Query 完成后传入）。"""

    page: int
    page_size: int
    sort: QuestionSort = QuestionSort.LATEST


@dataclass(frozen=True, slots=True)
class GetQuestionQuery:
    """详情查询参数。"""

    question_id: UUID
