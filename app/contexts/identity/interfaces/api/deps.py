from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.contexts.identity.domain.user import Role, User
from app.contexts.identity.infrastructure.repository import SqlAlchemyUserRepository
from app.contexts.identity.infrastructure.token_service import JwtTokenService
from app.shared.engine import get_session

_bearer = HTTPBearer(auto_error=False)
# 模块级单例：不每请求重建（JWT 校验无请求级状态）
token_service = JwtTokenService(get_settings().jwt_secret)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """解析 Authorization: Bearer → 校验 Access 令牌 → 查库返回当前用户（2.3）。"""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未提供认证令牌")
    user_id = token_service.verify_access(credentials.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌无效或已过期")
    user = await SqlAlchemyUserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    return user


def require_roles(*roles: Role) -> Callable[..., Awaitable[User]]:
    """RBAC 依赖工厂：要求当前用户属于指定角色之一。"""

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足")
        return user

    return _checker


# 公开供给面：下游上下文（如 qa）只经此别名消费当前用户，
# 不直接 import identity.domain（context-map 边界规则 4 的 interfaces 层例外）
CurrentUser = Annotated[User, Depends(get_current_user)]
