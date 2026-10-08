from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from app.contexts.identity.domain.user import User

# 令牌 TTL：签发与存储共用同一常量，避免两处漂移
ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)

# 登录失败锁定参数（US-L04，2026-09-29 裁定：全 identifier 统一计数，5 次/15 分钟窗口）
LOGIN_FAILURE_THRESHOLD = 5
LOGIN_LOCKOUT_WINDOW = timedelta(minutes=15)


class PasswordHasher(Protocol):
    """密码哈希端口：application 定义，infrastructure 提供 bcrypt 实现。"""

    async def hash(self, plain: str) -> str:
        """将明文密码转为 bcrypt 哈希。"""
        ...

    async def verify(self, plain: str, hashed: str) -> bool:
        """校验明文密码与哈希是否匹配。"""
        ...


@dataclass(frozen=True, slots=True)
class TokenPair:
    """签发出的令牌对。"""

    access_token: str
    refresh_token: str
    refresh_jti: UUID


class TokenService(Protocol):
    """JWT 签发与校验端口：JWT 细节不进 application。"""

    def issue_access(self, user: User) -> str:
        """签发 Access 令牌（typ=access，TTL 15min）。"""
        ...

    def issue_refresh(self, user: User) -> tuple[str, UUID]:
        """签发 Refresh 令牌（typ=refresh + jti，TTL 7d），返回 (token, jti)。"""
        ...

    def verify_access(self, token: str) -> UUID | None:
        """校验 Access 令牌：签名/过期/typ 全通过返回 user_id，否则 None。"""
        ...

    def decode_refresh(self, token: str) -> tuple[UUID, UUID] | None:
        """解码 Refresh 令牌：返回 (user_id, jti)，无效返回 None。"""
        ...


class RefreshTokenStore(Protocol):
    """Refresh 令牌存储端口：Redis 实现，支持原子消耗（防并发重放）。"""

    async def save(self, jti: UUID, user_id: UUID, ttl: timedelta) -> None:
        """保存 refresh:{jti} → user_id，TTL 后自动过期。"""
        ...

    async def consume(self, jti: UUID) -> UUID | None:
        """原子"校验并消耗"：存在则删除并返回 user_id，不存在返回 None（GETDEL 语义）。"""
        ...

    async def revoke(self, jti: UUID) -> None:
        """吊销：删除 refresh:{jti}，幂等。"""
        ...


class LoginAttemptGuard(Protocol):
    """登录失败计数/锁定守卫端口（US-L04）。

    锁定时瞬态运维状态，非领域不变式（aggregates.md User 不变式未列它）——
    用 Redis 计数器实现，不动 User 聚合、无迁移（2026-09-29 裁定）。
    """

    async def check_locked(self, identifier: str) -> bool:
        """是否已锁定（失败次数 ≥ 阈值）。"""
        ...

    async def record_failure(self, identifier: str) -> None:
        """记录一次登录失败（计数 + 刷新窗口 TTL）。"""
        ...

    async def clear(self, identifier: str) -> None:
        """登录成功清零失败计数（幂等）。"""
        ...
