from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AskQuestionRequest(BaseModel):
    """POST /api/v1/questions 请求体。

    str_strip_whitespace 在长度约束之前生效：纯空白标题/正文 strip 后为空 → 422。
    tags 可选（迭代 4，Q03）：schema 只拦原始数量滥用（≤20 松上限）与类型/结构错误
    （数组形 422）；去重后 ≤5、白名单字符等语义校验在领域层（字符串形 422），
    两种 422 形态见 api-contract-notes。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=20)


class PostAnswerRequest(BaseModel):
    """POST /api/v1/questions/{qid}/answers 请求体（US-A01）。

    正文与问题共用 1~5000 字约束；作者只取令牌，绝不取自请求体。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=5000)


class VoteRequest(BaseModel):
    """投票请求体（US-V01）：direction 枚举即校验，非法值 422。"""

    model_config = ConfigDict(extra="forbid")

    direction: Literal["up", "down"]


class CommentRequest(BaseModel):
    """评论请求体（US-C01）：正文复用 Body 值对象约束（v3 自裁：1~5000 字）。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=5000)


class CommentResponse(BaseModel):
    """评论白名单（按时间正序返回，1.3 功能域 9）。"""

    id: UUID
    body: str
    author_id: UUID
    created_at: datetime


class QuestionResponse(BaseModel):
    """问题响应白名单：不含任何内部字段。tags 为规范名列表（迭代 4，Q03）。"""

    id: UUID
    title: str
    body: str
    author_id: UUID
    created_at: datetime
    tags: list[str] = Field(default_factory=list)


class QuestionListItem(BaseModel):
    """列表条目白名单：不含正文（正文最长 5000 字，列表页不需要）与任何内部字段（S-12）。

    tags 为迭代 4 新增字段（增量、向后兼容）。
    """

    id: UUID
    title: str
    author_id: UUID
    created_at: datetime
    tags: list[str] = Field(default_factory=list)


class TagListResponse(BaseModel):
    """标签目录响应（US-T01，访客可用）：码点序、同名唯一（T02）。"""

    tags: list[str]


class QuestionListResponse(BaseModel):
    """分页契约：total_pages = ceil(total/page_size)，空库为 0。"""

    items: list[QuestionListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class AnswerResponse(BaseModel):
    """回答白名单（US-A01/A05）：votes 为净票数（v3 裁定 #1，可为负）。"""

    id: UUID
    body: str
    author_id: UUID
    created_at: datetime
    votes: int
    is_accepted: bool
    comments: list[CommentResponse] = Field(default_factory=list)


class QuestionDetailResponse(BaseModel):
    """详情白名单。

    answers 按 D2 定稿排序（已采纳恒最前 > 净票数降序 > 时间正序）；
    accepted_answer_id 顶层返回便于前端直接定位（v3 裁定 #3）；
    comments 为题评（US-C01，按时间正序）；tags 迭代 1 恒为空列表（分支 3 就位）。
    """

    id: UUID
    title: str
    body: str
    author_id: UUID
    created_at: datetime
    accepted_answer_id: UUID | None
    tags: list[str] = Field(default_factory=list)
    answers: list[AnswerResponse] = Field(default_factory=list)
    comments: list[CommentResponse] = Field(default_factory=list)


class EditQuestionRequest(BaseModel):
    """PATCH /api/v1/questions/{id} 请求体（US-Q08；裁定 D6：仅标题+正文，标签不可编辑）。

    PATCH 部分更新：title/body 均可选、至少给一个（模型级校验，缺失即 422 数组形）；
    给哪个改哪个，缺省侧沿用既有值（用例合并）。字符串形 422 由领域值对象兜底。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=100)
    body: str | None = Field(default=None, min_length=1, max_length=5000)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> EditQuestionRequest:
        if self.title is None and self.body is None:
            raise ValueError("至少提供 title 或 body 之一")
        return self
