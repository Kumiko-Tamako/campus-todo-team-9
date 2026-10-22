"""登录用例：查用户 → 失败计数守卫（US-L04）→ bcrypt 验证 → 签发双令牌（US-L01/L02）。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.contexts.identity.application.commands import LoginCommand
from app.contexts.identity.application.ports import (
    REFRESH_TOKEN_TTL,
    LoginAttemptGuard,
    PasswordHasher,
    RefreshTokenStore,
    TokenService,
)
from app.contexts.identity.domain.errors import AccountLockedError, InvalidCredentialsError
from app.contexts.identity.domain.repository import UserRepository
from app.contexts.identity.domain.user import User


@dataclass(frozen=True, slots=True)
class LoginResult:
    """登录成功产出：用户 + 令牌对。"""

    user: User
    access_token: str
    refresh_token: str
    refresh_jti: UUID


class LoginUseCase:
    """登录用例：失败守卫 → 按学号/工号查用户 → bcrypt 验证 → 签发双令牌。

    锁定语义（US-L04，2026-09-29 裁定）：阈值内连续失败计数，达到阈值→423；
    失败计数对全 identifier 统一记录（不区分账号是否存在，防枚举）；
    登录成功清零。锁定失败不区分 401/423 之外的账号状态。
    """

    def __init__(
        self,
        repository: UserRepository,
        hasher: PasswordHasher,
        token_service: TokenService,
        refresh_store: RefreshTokenStore,
        login_attempt_guard: LoginAttemptGuard,
    ) -> None:
        self._repository = repository
        self._hasher = hasher
        self._token_service = token_service
        self._refresh_store = refresh_store
        self._login_attempt_guard = login_attempt_guard

    async def execute(self, command: LoginCommand) -> LoginResult:
        if await self._login_attempt_guard.check_locked(command.identifier):
            raise AccountLockedError("尝试次数过多，账号临时锁定，请稍后再试")

        user = await self._find_by_identifier(command.identifier)
        # 用户不存在与密码错误统一同一异常与消息（防枚举）；两者都计一次失败
        if user is None:
            await self._login_attempt_guard.record_failure(command.identifier)
            raise InvalidCredentialsError("学号/工号或密码错误")

        password_ok = await self._hasher.verify(command.password, user.password_hash.value)
        if not password_ok:
            await self._login_attempt_guard.record_failure(command.identifier)
            raise InvalidCredentialsError("学号/工号或密码错误")

        await self._login_attempt_guard.clear(command.identifier)

        access_token = self._token_service.issue_access(user)
        refresh_token, jti = self._token_service.issue_refresh(user)
        await self._refresh_store.save(jti, user.id, REFRESH_TOKEN_TTL)
        return LoginResult(
            user=user,
            access_token=access_token,
            refresh_token=refresh_token,
            refresh_jti=jti,
        )

    async def _find_by_identifier(self, identifier: str) -> User | None:
        # identifier 判定：T 前缀 → 工号，否则 → 学号
        if identifier.startswith("T"):
            return await self._repository.get_by_staff_id(identifier)
        return await self._repository.get_by_student_id(identifier)