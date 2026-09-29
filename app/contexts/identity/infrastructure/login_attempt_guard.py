"""登录失败锁定守卫的 Redis 实现（US-L04）。

- key：`login:fail:{identifier}` → 失败计数值，EX 窗口 TTL 自动过期
- record_failure 用 INCR + EXPIRE 流水线：INCR 原子自增，EXPIRE 每次刷新窗口
  （滑动窗口语义：连续失败持续延长锁定前剩余窗口）
- 锁定是瞬态运维状态，非领域不变式（aggregates.md User 未列它）——不落库、无迁移
- 每次操作动态取 get_redis() 当前单例：测试 reset_redis() 后新实例立即可见
  （与 RedisRefreshTokenStore 同决策）
"""

from __future__ import annotations

from app.contexts.identity.application.ports import (
    LOGIN_FAILURE_THRESHOLD,
    LOGIN_LOCKOUT_WINDOW,
)
from app.shared.redis import get_redis


class RedisLoginAttemptGuard:
    """LoginAttemptGuard 端口的 Redis 实现（2026-09-29 裁定：全 identifier 统一计数）。"""

    _PREFIX = "login:fail:"

    def _key(self, identifier: str) -> str:
        return f"{self._PREFIX}{identifier}"

    async def check_locked(self, identifier: str) -> bool:
        raw = await get_redis().get(self._key(identifier))
        if raw is None:
            return False
        try:
            return int(raw) >= LOGIN_FAILURE_THRESHOLD
        except ValueError:  # 键被污染（理论不可达）：不拦截登录，留待 TTL 过期自愈
            return False

    async def record_failure(self, identifier: str) -> None:
        # INCR + EXPIRE 组 MULTI/EXEC 一次执行（pipeline 默认 transaction=True）：
        # 消除"INCR 成功、EXPIRE 未达"留下永不过期键（永久误锁）的窗口
        key = self._key(identifier)
        pipe = get_redis().pipeline()
        pipe.incr(key)
        pipe.expire(key, int(LOGIN_LOCKOUT_WINDOW.total_seconds()))
        await pipe.execute()

    async def clear(self, identifier: str) -> None:
        await get_redis().delete(self._key(identifier))