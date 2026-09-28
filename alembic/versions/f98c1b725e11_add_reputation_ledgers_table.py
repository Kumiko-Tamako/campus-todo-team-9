"""add reputation_ledgers table

Revision ID: f98c1b725e11
Revises: b4e91f7a2c35
Create Date: 2026-09-28 12:15:33.235262

"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'f98c1b725e11'
down_revision: str | None = 'b4e91f7a2c35'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 声誉流水表（US-REP01/REP02）：只追加；账面总值 = 流水累加不落列
    # （aggregates.md 不变式 3）。幂等 = (source, event_id) 复合唯一：
    # vote 侧 event_id=票行主键 vote_id（不可改票），accept 侧=事件 uuid4
    # （一答一采纳）——两异源 UUID 以 source 隔离语义（3.6 细案 v3.1 表设计 ②）；
    # 并发双投递由仓储 ON CONFLICT DO NOTHING 原子判定，恰落一行。
    # occurred_at 为事件时间（非处理时间）：重试/乱序下倒序展示仍忠实时序。
    op.create_table(
        'reputation_ledgers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source', sa.String(length=8), nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=50), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # 事件幂等唯一索引（不变式 1）
    op.create_index(
        'uq_reputation_source_event', 'reputation_ledgers', ['source', 'event_id'], unique=True
    )
    # 本人流水倒序读取路径（US-REP02）
    op.create_index(
        'ix_reputation_user_occurred', 'reputation_ledgers', ['user_id', 'occurred_at']
    )


def downgrade() -> None:
    op.drop_index('ix_reputation_user_occurred', table_name='reputation_ledgers')
    op.drop_index('uq_reputation_source_event', table_name='reputation_ledgers')
    op.drop_table('reputation_ledgers')
