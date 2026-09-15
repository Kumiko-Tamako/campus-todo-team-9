from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.contexts.qa.domain.question import Question


class QuestionRepository(Protocol):
    """问题聚合持久化端口：domain 定义接口，infrastructure 实现。"""

    async def add(self, question: Question) -> None:
        """新增问题（聚合整体落库）。"""
        ...

    async def get_by_id(self, question_id: UUID) -> Question | None:
        """按问题 ID 查询（2.4 集成测试回读使用，2.6 详情直接复用）。"""
        ...

    async def list_paginated(self, page: int, page_size: int) -> tuple[list[Question], int]:
        """分页列出问题：按发布时间新→旧，返回（当前页聚合列表，总条数）。

        迭代 1 仅"按最新排序"；投票排序属迭代 2（US-Q02），不进端口。
        """
        ...
