"""标签目录浏览用例（US-T01，访客可用）：返回目录全部标签名。"""

from __future__ import annotations

from app.contexts.qa.domain.repository import TagCatalogRepository
from app.contexts.qa.domain.tag import Tag


class ListTagsUseCase:
    """GET /tags：返回目录全部标签（显示名 = 建目时规范名）。

    排序在应用层完成（v6 定稿）：Python 码点序（locale 无关、跨环境确定），
    同名唯一由目录不变式（lower(name) 唯一索引）天然保证（1.3 功能域 10 L227）。
    """

    def __init__(self, tag_repository: TagCatalogRepository) -> None:
        self._tag_repository = tag_repository

    async def execute(self) -> list[Tag]:
        tags = await self._tag_repository.list_all()
        return sorted(tags, key=lambda t: t.value)
