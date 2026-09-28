"""reputation 接口 schema：白名单响应模型（US-REP02）。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReputationEntryResponse(BaseModel):
    """单条流水（白名单：不含 user_id——路径已定位本人账本）。"""

    source: str
    event_id: UUID
    delta: int
    reason: str
    occurred_at: datetime


class ReputationResponse(BaseModel):
    """GET /api/v1/users/{user_id}/reputation 响应（v3.1 裁定 4：仅本人可见）。

    entries 不分页（v3.1 裁定：流水量小，对齐 GET /tags 惯例）。
    """

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    total: int
    entries: list[ReputationEntryResponse]
