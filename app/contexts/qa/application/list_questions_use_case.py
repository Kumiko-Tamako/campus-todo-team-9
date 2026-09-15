"""列表用例：分页读取问题（US-Q02，访客可用；迭代 1 仅按最新排序）。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.contexts.qa.application.queries import ListQuestionsQuery
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import QuestionRepository


@dataclass(frozen=True, slots=True)
class QuestionPage:
    """列表页读取结果。

    total_pages = ceil(total/page_size)，空库为 0（2.8 openapi 契约，
    前端据此渲染页码与空态）。
    """

    items: list[Question]
    total: int
    page: int
    page_size: int
    total_pages: int


class ListQuestionsUseCase:
    """分页列表：排序与切片委托仓储，本用例只组装分页元数据。"""

    def __init__(self, repository: QuestionRepository) -> None:
        self._repository = repository

    async def execute(self, query: ListQuestionsQuery) -> QuestionPage:
        items, total = await self._repository.list_paginated(query.page, query.page_size)
        return QuestionPage(
            items=items,
            total=total,
            page=query.page,
            page_size=query.page_size,
            total_pages=math.ceil(total / query.page_size) if total else 0,
        )
