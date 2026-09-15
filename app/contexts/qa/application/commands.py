from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AskQuestionCommand:
    """提问用例的输入命令。author_id 来自认证依赖（当前登录用户），绝不来自请求体。"""

    title: str
    body: str
    author_id: UUID
