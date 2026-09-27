from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.contexts.qa.domain.comment import CommentTarget
from app.contexts.qa.domain.vote import VoteDirection, VoteTarget


@dataclass(frozen=True, slots=True)
class AskQuestionCommand:
    """提问用例的输入命令。author_id 来自认证依赖（当前登录用户），绝不来自请求体。"""

    title: str
    body: str
    author_id: UUID


@dataclass(frozen=True, slots=True)
class PostAnswerCommand:
    """回答用例的输入命令。author_id 来自认证依赖，绝不来自请求体（US-A01）。"""

    question_id: UUID
    body: str
    author_id: UUID


@dataclass(frozen=True, slots=True)
class VoteOnCommand:
    """投票用例的输入命令。user_id 来自认证依赖；方向/目标类型已在 schema 层枚举校验（US-V01）。"""

    target_type: VoteTarget
    target_id: UUID
    direction: VoteDirection
    user_id: UUID


@dataclass(frozen=True, slots=True)
class AcceptAnswerCommand:
    """采纳用例的输入命令。actor_id 来自认证依赖，须为问题提问者（US-V03）。

    问题由 answer.question_id 定位（端点 `POST /answers/{id}/accept` 路径无 question 段）。
    """

    answer_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class CreateCommentCommand:
    """评论用例的输入命令。author_id 来自认证依赖，绝不来自请求体（US-C01）。"""

    target_type: CommentTarget
    target_id: UUID
    body: str
    author_id: UUID
