from __future__ import annotations

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.contexts.qa.domain.answer import Answer
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.tag import Tag
from app.contexts.qa.domain.vote import Vote, VoteTarget


class QuestionSort(StrEnum):
    """列表排序口径（US-Q02 + 1.3 L161-164，v3 裁定 #4：迭代 2 实现）。"""

    LATEST = "latest"  # 发布时间新→旧（默认）
    VOTES = "votes"  # 净票数高→低（v3 裁定 #1：up − down）


class QuestionRepository(Protocol):
    """问题聚合持久化端口：domain 定义接口，infrastructure 实现。"""

    async def add(self, question: Question) -> None:
        """新增问题（聚合整体落库）。"""
        ...

    async def update(self, question: Question) -> None:
        """更新既有问题聚合（采纳双写 accepted_answer_id，US-V03 迭代 3）。"""
        ...

    async def get_by_id(self, question_id: UUID) -> Question | None:
        """按问题 ID 查询（2.4 集成测试回读使用，2.6 详情直接复用）。"""
        ...

    async def list_paginated(
        self, page: int, page_size: int, sort: QuestionSort = QuestionSort.LATEST
    ) -> tuple[list[Question], int]:
        """分页列出问题，返回（当前页聚合列表，总条数）。

        sort=latest：按发布时间新→旧；sort=votes：按净票数高→低（v3 裁定 #4）。
        两种排序均以 id 作确定性 tiebreaker，跨页不重复/不漏项。
        """
        ...


class AnswerRepository(Protocol):
    """回答聚合持久化端口：domain 定义接口，infrastructure 实现（迭代 2）。"""

    async def add(self, answer: Answer) -> None:
        """新增回答（聚合整体落库）。"""
        ...

    async def update(self, answer: Answer) -> None:
        """更新既有回答聚合（采纳翻转 is_accepted，US-V03 迭代 3）。"""
        ...

    async def get_by_id(self, answer_id: UUID) -> Answer | None:
        """按回答 ID 查询（投票/采纳定位回答使用）。"""
        ...

    async def list_by_question(self, question_id: UUID) -> list[Answer]:
        """列出问题的全部回答，按 D2 定稿排序：已采纳恒最前，其余按净票数降序。

        净票数为读时聚合（v3 裁定 #1：up − down），重建时填入 Answer.votes_count。
        """
        ...


class VoteRepository(Protocol):
    """投票持久化端口：domain 定义接口，infrastructure 实现（迭代 2）。"""

    async def find_by_user_target(
        self, user_id: UUID, target_type: VoteTarget, target_id: UUID
    ) -> Vote | None:
        """查用户对某目标的既有票（不分方向）：一人一票的事前检查。"""
        ...

    async def add(self, vote: Vote) -> None:
        """落一票。并发重复票由复合唯一索引兜底（IntegrityError → 409）。"""
        ...


class CommentRepository(Protocol):
    """评论持久化端口：domain 定义接口，infrastructure 实现（迭代 3，US-C01）。"""

    async def add(self, comment: Comment) -> None:
        """新增评论（多态 target：题评挂 Question、答评挂 Answer）。"""
        ...

    async def list_by_target(
        self, target_type: CommentTarget, target_id: UUID
    ) -> list[Comment]:
        """列出某目标的全部评论，按时间正序（1.3 功能域 9：答评按时间正序排列）。"""
        ...


class TagCatalogRepository(Protocol):
    """TagCatalog 持久化端口（迭代 4，US-T01/T02）：目录 = tags 表全局唯一。

    get-or-create 语义（随用随建，T02）：同名（lower 归一键）命中既有行则复用，
    未命中则插入；并发双插由 lower(name) 唯一索引兜底，实现内 savepoint 重试。
    """

    async def get_or_create(self, tag: Tag) -> Tag:
        """按归并键取目录内标签，不存在则创建（幂等）。"""
        ...

    async def list_all(self) -> list[Tag]:
        """列出目录全部标签（显示名 = 建目时的规范名）。"""
        ...
