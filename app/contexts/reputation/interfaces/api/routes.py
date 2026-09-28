"""reputation 接口路由（分支 4，US-REP02）：查询本人声誉总值与流水。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.deps import CurrentUser
from app.contexts.reputation.application.get_reputation_use_case import GetReputationUseCase
from app.contexts.reputation.infrastructure.repository import (
    SqlAlchemyReputationLedgerRepository,
)
from app.contexts.reputation.interfaces.api.schemas import (
    ReputationEntryResponse,
    ReputationResponse,
)
from app.shared.engine import get_session

reputation_router = APIRouter(prefix="/api/v1/users", tags=["reputation"])


@reputation_router.get(
    "/{user_id}/reputation",
    response_model=ReputationResponse,
    summary="查询本人声誉总值与变动流水（仅本人，US-REP02；他人 403）",
)
async def get_reputation(
    user_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> ReputationResponse:
    """仅本人可见（v3.1 裁定 4；Gherkin 功能域 11 场景 3 字面"查询自己的声誉"）。

    403（非 404）：user_id 在问题/回答的 author_id 已公开，无存在性可泄露，
    403 语义最准确；流水为空时返回 total=0 + 空列表（200）。
    """
    if user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="仅可查询本人声誉"
        )
    use_case = GetReputationUseCase(SqlAlchemyReputationLedgerRepository(session))
    view = await use_case.execute(user_id)
    return ReputationResponse(
        user_id=view.user_id,
        total=view.total,
        entries=[
            ReputationEntryResponse(
                source=e.source.value,
                event_id=e.event_id,
                delta=e.delta,
                reason=e.reason,
                occurred_at=e.occurred_at,
            )
            for e in view.entries
        ],
    )
