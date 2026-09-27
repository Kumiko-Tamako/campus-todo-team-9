"""add partial unique index one accepted answer per question

Revision ID: 7b8b074ad539
Revises: 124cca2a07aa
Create Date: 2026-09-23 10:43:11.741362

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = '7b8b074ad539'
down_revision: str | None = '124cca2a07aa'
branch_labels: str | None = None
depends_on: str | None = None

# 每题保留最早（created_at, id）一条采纳答案，其余取消采纳
_CLEAN_DUP_ACCEPTED = """
WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (
        PARTITION BY question_id ORDER BY created_at ASC, id ASC
    ) AS rn
    FROM answers WHERE is_accepted
)
UPDATE answers SET is_accepted = false
WHERE is_accepted AND id NOT IN (SELECT id FROM ranked WHERE rn = 1)
"""

# 问题引用对齐到保留项
_ALIGN_QUESTION_REF = """
WITH keep AS (
    SELECT DISTINCT ON (question_id) question_id, id
    FROM answers WHERE is_accepted ORDER BY question_id, created_at ASC, id ASC
)
UPDATE questions q SET accepted_answer_id = keep.id
FROM keep WHERE q.id = keep.question_id
  AND q.accepted_answer_id IS DISTINCT FROM keep.id
"""

# 引用指向的答案已非采纳态 → 置 NULL（并发覆盖残留的孤儿引用）
_NULL_ORPHAN_REF = """
UPDATE questions SET accepted_answer_id = NULL
WHERE accepted_answer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM answers a
      WHERE a.id = questions.accepted_answer_id AND a.is_accepted
  )
"""


def upgrade() -> None:
    # ### 人工审核调整（2026-09-23）：AC-12 暴力测试暴露应用层竞态，
    # 已在库留下同题多采纳脏数据；先清理再建部分唯一索引 ###
    op.execute(_CLEAN_DUP_ACCEPTED)
    op.execute(_ALIGN_QUESTION_REF)
    op.execute(_NULL_ORPHAN_REF)
    op.create_index(
        'uq_answers_one_accepted_per_question', 'answers', ['question_id'],
        unique=True, postgresql_where=sa.text('is_accepted')
    )


def downgrade() -> None:
    op.drop_index('uq_answers_one_accepted_per_question', table_name='answers')
