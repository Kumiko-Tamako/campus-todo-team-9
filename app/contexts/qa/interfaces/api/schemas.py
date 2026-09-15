from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AskQuestionRequest(BaseModel):
    """POST /api/v1/questions 请求体。

    str_strip_whitespace 在长度约束之前生效：纯空白标题/正文 strip 后为空 → 422。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=5000)


class QuestionResponse(BaseModel):
    """问题响应白名单：不含任何内部字段。"""

    id: UUID
    title: str
    body: str
    author_id: UUID
    created_at: datetime


class QuestionListItem(BaseModel):
    """列表条目白名单：不含正文（正文最长 5000 字，列表页不需要）与任何内部字段（S-12）。"""

    id: UUID
    title: str
    author_id: UUID
    created_at: datetime


class QuestionListResponse(BaseModel):
    """分页契约：total_pages = ceil(total/page_size)，空库为 0。"""

    items: list[QuestionListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class QuestionDetailResponse(BaseModel):
    """详情白名单。

    tags/answers 迭代 1 恒为空列表（答案/标签功能阶段 3 就位；
    answers 元素结构届时定稿，当前仅占位）。
    """

    id: UUID
    title: str
    body: str
    author_id: UUID
    created_at: datetime
    tags: list[str] = Field(default_factory=list)
    answers: list[str] = Field(default_factory=list)
