"""声誉记账 Celery 任务（分支 4）：薄壳——载荷反序列化后调应用层记账函数。

worker 数据库策略（v3.1 必修项 1）：任务内 asyncio.run() 每次新建事件循环，
**强制 NullPool 独立引擎**——池化连接绑定创建它的 loop，跨 asyncio.run 复用必挂
（"attached to a different loop"）；NullPool 每次取用即新建连接，对多 loop 免疫
（与 engine.py 默认路径同源决策）。worker 记账量小，每任务新建连接可接受；
引擎对象进程内缓存（NullPool 不持有连接，跨 loop 安全），第十二路探针
R-08 连续多任务实证无跨 loop 残留。

重试口径（v3.1 G2/毒消息防循环）：
- 瞬态失败（DB 连接类/服务端错误）→ autoretry 退避重试，幂等由
  (source, event_id) 唯一索引兜底；
- 载荷非法（未知 target/direction 等应用层 ValueError）→ 不在 autoretry_for
  内，直接失败不重试（记错误日志后丢弃，防 acks_late 无限重投）。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]  # asyncpg 无 py.typed，mypy strict 下豁免
from sqlalchemy import pool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.contexts.reputation.application.apply_reputation import (
    AcceptEventPayload,
    VoteEventPayload,
    apply_accept_event,
    apply_vote_event,
)
from app.contexts.reputation.infrastructure.celery_app import celery_app
from app.contexts.reputation.infrastructure.repository import (
    SqlAlchemyReputationLedgerRepository,
)

logger = logging.getLogger(__name__)

_worker_session_factory: async_sessionmaker[Any] | None = None


def _get_worker_session_factory() -> async_sessionmaker[Any]:
    """worker 专用会话工厂：独立 NullPool 引擎（进程内缓存，跨 loop 安全）。"""
    global _worker_session_factory
    if _worker_session_factory is None:
        settings = get_settings()
        engine = create_async_engine(
            settings.database_url,
            poolclass=pool.NullPool,
            connect_args={
                "timeout": settings.db_connect_timeout,
                "server_settings": {
                    "statement_timeout": str(settings.db_statement_timeout_ms),
                    "lock_timeout": str(settings.db_lock_timeout_ms),
                },
            },
        )
        _worker_session_factory = async_sessionmaker(engine, expire_on_commit=False)
        logger.info("worker 专用 NullPool 引擎已创建")
    return _worker_session_factory


def _to_uuid(value: Any) -> UUID:
    """载荷回转：kombu JSON 出入为字符串（UUID → str），统一在此还原。"""
    return value if isinstance(value, UUID) else UUID(str(value))


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _vote_payload(data: dict[str, Any]) -> VoteEventPayload:
    return VoteEventPayload(
        vote_id=_to_uuid(data["vote_id"]),
        user_id=_to_uuid(data["user_id"]),
        target_type=str(data["target_type"]),
        target_id=_to_uuid(data["target_id"]),
        direction=str(data["direction"]),
        target_author_id=_to_uuid(data["target_author_id"]),
        occurred_at=_to_datetime(data["occurred_at"]),
    )


def _accept_payload(data: dict[str, Any]) -> AcceptEventPayload:
    return AcceptEventPayload(
        event_id=_to_uuid(data["event_id"]),
        answer_id=_to_uuid(data["answer_id"]),
        answer_author_id=_to_uuid(data["answer_author_id"]),
        occurred_at=_to_datetime(data["occurred_at"]),
    )


# 瞬态错误族：SQLAlchemy 包装层 + asyncpg 连接层 + 内置 TimeoutError（黑洞建连超时）
# ——v3.1 必修项 3；ValueError（毒载荷）不在其中，失败即弃
_RETRYABLE = (
    SQLAlchemyError,
    asyncpg.exceptions.PostgresError,
    OSError,
    TimeoutError,
)


async def _apply_vote(data: dict[str, Any]) -> bool:
    async with _get_worker_session_factory()() as session:
        repo = SqlAlchemyReputationLedgerRepository(session)
        recorded = await apply_vote_event(_vote_payload(data), repo)
        await session.commit()
        return recorded


async def _apply_accept(data: dict[str, Any]) -> bool:
    async with _get_worker_session_factory()() as session:
        repo = SqlAlchemyReputationLedgerRepository(session)
        recorded = await apply_accept_event(_accept_payload(data), repo)
        await session.commit()
        return recorded


@celery_app.task(
    name="reputation.apply_vote_delta",
    bind=True,
    autoretry_for=_RETRYABLE,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
)
def apply_vote_delta(self: Any, payload: dict[str, Any]) -> bool:
    """投票事件记账（US-REP01）。载荷 = 发布端事件 dict（UUID/datetime 已字符串化）。"""
    recorded = asyncio.run(_apply_vote(payload))
    if not recorded:
        logger.info(
            "投票事件跳过（自投或已记账）: vote_id=%s", payload.get("vote_id")
        )
    return recorded


@celery_app.task(
    name="reputation.apply_accept_bonus",
    bind=True,
    autoretry_for=_RETRYABLE,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
)
def apply_accept_bonus(self: Any, payload: dict[str, Any]) -> bool:
    """采纳事件记账（US-REP01）。"""
    recorded = asyncio.run(_apply_accept(payload))
    if not recorded:
        logger.info("采纳事件已记账（幂等跳过）: event_id=%s", payload.get("event_id"))
    return recorded
