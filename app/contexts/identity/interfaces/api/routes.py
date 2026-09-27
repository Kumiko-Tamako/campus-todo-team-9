from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.contexts.identity.application.commands import LoginCommand, RegisterCommand
from app.contexts.identity.application.login_use_case import LoginUseCase
from app.contexts.identity.application.ports import ACCESS_TOKEN_TTL, REFRESH_TOKEN_TTL
from app.contexts.identity.application.register_use_case import RegisterUseCase
from app.contexts.identity.domain.errors import (
    EmailAlreadyExistsError,
    IdentityAlreadyExistsError,
    IdentityDomainError,
    InvalidCredentialsError,
)
from app.contexts.identity.domain.user import User
from app.contexts.identity.infrastructure.password_hasher import BcryptPasswordHasher
from app.contexts.identity.infrastructure.refresh_store import RedisRefreshTokenStore
from app.contexts.identity.infrastructure.repository import SqlAlchemyUserRepository
from app.contexts.identity.infrastructure.token_service import JwtTokenService
from app.contexts.identity.interfaces.api.deps import get_current_user
from app.contexts.identity.interfaces.api.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenPairResponse,
)
from app.shared.engine import get_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 模块级单例：令牌服务与刷新存储无请求级状态
_token_service = JwtTokenService(get_settings().jwt_secret)
_refresh_store = RedisRefreshTokenStore()


def _build_register_use_case(session: AsyncSession) -> RegisterUseCase:
    """组装注册用例：仓储 + 哈希器依赖注入。"""
    return RegisterUseCase(SqlAlchemyUserRepository(session), BcryptPasswordHasher())


def _build_login_use_case(session: AsyncSession) -> LoginUseCase:
    """组装登录用例：仓储 + 哈希器 + 令牌服务 + 刷新存储。"""
    return LoginUseCase(
        SqlAlchemyUserRepository(session),
        BcryptPasswordHasher(),
        _token_service,
        _refresh_store,
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="注册（学生/教师分流）",
)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> RegisterResponse:
    use_case = _build_register_use_case(session)
    command = RegisterCommand(
        role=payload.role,
        email=payload.email,
        password=payload.password,
        student_id=payload.student_id,
        staff_id=payload.staff_id,
    )
    try:
        user = await use_case.execute(command)
    except (EmailAlreadyExistsError, IdentityAlreadyExistsError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IdentityDomainError as exc:  # 弱密码 / 缺身份 / 未知角色
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ValueError as exc:  # 值对象格式校验（学号/工号/邮箱）
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return RegisterResponse(
        id=user.id,
        role=user.role,
        email=user.email.value,
        student_id=user.student_id.value if user.student_id is not None else None,
        staff_id=user.staff_id.value if user.staff_id is not None else None,
        created_at=user.created_at,
    )


@router.post(
    "/login",
    response_model=TokenPairResponse,
    summary="登录（学号/工号 + 密码 → JWT 双令牌）",
)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> TokenPairResponse:
    use_case = _build_login_use_case(session)
    try:
        result = await use_case.execute(
            LoginCommand(identifier=payload.identifier, password=payload.password)
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    return TokenPairResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
    )


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    summary="刷新令牌（轮换：旧 Refresh 原子消耗，签发新对）",
)
async def refresh(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> TokenPairResponse:
    decoded = _token_service.decode_refresh(payload.refresh_token)
    if decoded is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效或已过期")
    user_id, jti = decoded
    # 先读用户再消耗令牌（跨存储顺序修正，第八路观察点 3）：DB 读失败返回 503 时
    # 令牌未被 GETDEL 烧毁，客户端按契约重试可成功；先消耗再读会让 503 重试必然 401。
    user = await SqlAlchemyUserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    consumed = await _refresh_store.consume(jti)
    if consumed is None or consumed != user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已失效")

    access_token = _token_service.issue_access(user)
    refresh_token, new_jti = _token_service.issue_refresh(user)
    await _refresh_store.save(new_jti, user.id, REFRESH_TOKEN_TTL)
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="退出登录（吊销 Refresh 令牌，幂等 204）",
)
async def logout(payload: RefreshRequest) -> Response:
    decoded = _token_service.decode_refresh(payload.refresh_token)
    if decoded is not None:
        _, jti = decoded
        await _refresh_store.revoke(jti)
    # 幂等：无效/已吊销令牌同样 204，不暴露令牌状态
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=RegisterResponse,
    summary="当前用户信息（受保护：需 Bearer Access 令牌）",
)
async def me(user: User = Depends(get_current_user)) -> RegisterResponse:
    return RegisterResponse(
        id=user.id,
        role=user.role,
        email=user.email.value,
        student_id=user.student_id.value if user.student_id is not None else None,
        staff_id=user.staff_id.value if user.staff_id is not None else None,
        created_at=user.created_at,
    )
