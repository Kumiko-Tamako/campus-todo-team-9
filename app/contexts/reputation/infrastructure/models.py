"""reputation 基础设施：ReputationLedger 流水表（分支 4，US-REP01/REP02）。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class ReputationLedgerModel(Base):
    """reputation_ledgers 表：声誉流水（只追加）。

    幂等 = (source, event_id) 复合唯一索引：vote 侧 event_id=票行主键 vote_id
    （不可改票，复投 409），accept 侧 event_id=事件 uuid4（一答一采纳）——
    两异源 UUID 以 source 隔离语义（v3.1 表设计 ②）。账面总值 = 流水累加
    不落列（aggregates.md 不变式 3）；occurred_at 为事件时间，倒序即流水展示序
    （重试/乱序投递下仍忠实于事件时序，v3.1 注记）。
    """

    __tablename__ = "reputation_ledgers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # 被记分用户（提问者/回答者），非投票者；删用户随账清（与既有 FK 惯例一致）
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # 事件幂等：同一事件重复投递只记一行（并发双投递由 ON CONFLICT 兜底）
        Index("uq_reputation_source_event", "source", "event_id", unique=True),
        # 本人流水倒序读取路径（US-REP02）
        Index("ix_reputation_user_occurred", "user_id", "occurred_at"),
    )
