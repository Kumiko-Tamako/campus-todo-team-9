from collections.abc import AsyncIterator

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import get_settings


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    if settings.db_pool_size > 0:
        # 池化模式（仅哨兵 >0 时启用；0 绝不能传入池——SQLAlchemy 的 pool_size=0 是无上限池）。
        # pre_ping/recycle 防 WSL2/Docker NAT 静默丢弃空闲连接；上限 = pool_size+max_overflow。
        return create_async_engine(
            settings.database_url,
            poolclass=pool.AsyncAdaptedQueuePool,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    # NullPool：不复用连接。代价是每次请求新建连接（本机 ~1ms），
    # 换取对 pytest 多事件循环 / uvicorn --reload 的免疫（默认路径，测试/CI 零影响）。
    return create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )


engine = _build_engine()
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
