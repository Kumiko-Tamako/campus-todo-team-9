"""add tags catalog and question_tags links

Revision ID: b4e91f7a2c35
Revises: 7b8b074ad539
Create Date: 2026-09-27 15:30:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'b4e91f7a2c35'
down_revision: str | None = '7b8b074ad539'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # tags 目录表（US-T01/T02）：name 存建目时规范名（显示名），String(50) 与 Tag 值对象上限一致；
    # key 存归并键（应用 str.lower 计算并落列——键单源，不用 PG lower(name) 表达式索引，
    # 规避 Python/PG 对个别码位（如 İ）lower 映射分歧导致的"查不到→撞索引→重查不到"死路，
    # 第九路 X-06 实证）
    op.create_table(
        'tags',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # 同名唯一（大小写不敏感，T02）：应用计算键列上的唯一索引
    op.create_index('uq_tags_key', 'tags', ['key'], unique=True)
    # 问题↔标签多对多（Q03）：复合主键防重复挂接；两侧 CASCADE（v6：孤儿标签保留，边随删）
    op.create_table(
        'question_tags',
        sa.Column('question_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tag_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['question_id'], ['questions.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('question_id', 'tag_id'),
    )
    # 按标签反查问题（发现域预留访问路径）
    op.create_index('ix_question_tags_tag', 'question_tags', ['tag_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_question_tags_tag', table_name='question_tags')
    op.drop_table('question_tags')
    op.drop_index('uq_tags_key', table_name='tags')
    op.drop_table('tags')
