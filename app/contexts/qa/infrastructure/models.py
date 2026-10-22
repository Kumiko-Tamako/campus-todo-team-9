import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class QuestionModel(Base):
    """questions 表：Question 聚合根的持久化（迭代 1：标题 + 正文 + 作者引用）。"""

    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # PG 不自动给外键建索引：CASCADE 删用户需按 author_id 找子行，故显式索引
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 2.5 列表按发布时间新→旧排序，索引提前就位
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # 采纳引用（US-V03 双写的本侧）：FK→answers SET NULL——采纳答案被删则引用自动清空；
    # 与 answers.question_id 构成环形引用，PG 允许（两列均可空/后写），插入序无约束冲突
    accepted_answer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answers.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 关闭态（US-Q08，迭代 5）：open/closed；server_default 让存量行随迁移自动归 open
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="open")


class AnswerModel(Base):
    """answers 表：Answer 聚合根的持久化（迭代 2）。

    is_accepted 本迭代恒 False，列先行落库，采纳行为随分支 2 的 accept() 使用。
    """

    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # CASCADE：删问题连删其回答；显式索引供 list_by_question 与 CASCADE 反查
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_accepted: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # 一题一采纳的库级兜底（AC-12 暴力测试发现应用层检查存在并发竞态）：
        # 部分唯一索引——同一 question_id 下 is_accepted=true 至多一行
        Index(
            "uq_answers_one_accepted_per_question",
            "question_id",
            unique=True,
            postgresql_where=text("is_accepted"),
        ),
    )


class VoteModel(Base):
    """votes 表：Vote 值对象的持久化（迭代 2，多态目标 question/answer）。

    一人一票 = 复合唯一索引 (user_id, target_type, target_id) 不分方向（v3 裁定 #5）；
    target_id 为多态引用（question 或 answer），不做库级外键，存在性由用例检查。
    """

    __tablename__ = "votes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(10), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # 事前检查（find_by_user_target）与并发兜底同用此索引
        Index("uq_votes_user_target", "user_id", "target_type", "target_id", unique=True),
        # 目标净票数聚合（answers 排序 / 列表 votes 排序）按 target 反查
        Index("ix_votes_target", "target_type", "target_id"),
    )


class CommentModel(Base):
    """comments 表：Comment 实体持久化（迭代 3，US-C01）。

    多态 target（题评挂 question / 答评挂 answer），与 votes 同模式不做库级外键，
    存在性由用例检查；宿主删除的清理语义随 Q08 定稿（台账遗留③同口径）。
    """

    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(String(10), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # 评论列表按 (target, created_at 正序) 读取（1.3 功能域 9）
        Index("ix_comments_target_created", "target_type", "target_id", "created_at"),
    )


class TagModel(Base):
    """tags 表：TagCatalog 目录行（迭代 4，US-T01/T02）。

    name 存建目时规范名（显示名）；key 存归并键（domain Tag.key，应用计算）。
    同名唯一 = key 列唯一索引——键由应用单侧计算并落列，**不用 PG lower(name) 表达式索引**：
    Python str.lower 对个别码位（如 İ U+0130）做全映射（→i̇ 两码位），PG lower 做简单
    映射（→i 一码位），两侧不一致会让"查不到→插入撞索引→重查仍查不到"成死路
    （第九路 X-06 实证 400）。key 单源后应用与库判定恒等。
    """

    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # 归并键：value.lower() 可能全映射膨胀（≤2 倍），上限取 100
    key: Mapped[str] = mapped_column(String(100), nullable=False)

    __table_args__ = (Index("uq_tags_key", "key", unique=True),)


class QuestionTagModel(Base):
    """question_tags 关联表：问题↔标签多对多（迭代 4，Q03）。

    复合主键天然防同一 (question, tag) 重复挂接；两侧 FK CASCADE——
    删问题或删标签都自动清理关联行（目录孤儿标签保留，v6 定稿：随用随建不回收）。
    """

    __tablename__ = "question_tags"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (
        # 按标签反查问题（未来发现域）与列表批量装配 tags 的访问路径
        Index("ix_question_tags_tag", "tag_id"),
    )
