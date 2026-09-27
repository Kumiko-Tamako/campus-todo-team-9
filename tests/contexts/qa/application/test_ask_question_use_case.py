"""AskQuestionUseCase 单元测试：fake 仓储，不连库（进 CI）。

迭代 4：目录 fake 为每个标签分配稳定 id（get-or-create 语义的内存等价），
用例编排 resolve（去重/≤5/白名单）→ get_or_create → Question.ask(tags)。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.contexts.qa.application.ask_question_use_case import AskQuestionUseCase
from app.contexts.qa.application.commands import AskQuestionCommand
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.tag import Tag


class FakeQuestionRepository:
    """记录 add 调用的内存仓储。"""

    def __init__(self) -> None:
        self.added: list[Question] = []

    async def add(self, question: Question) -> None:
        self.added.append(question)

    async def get_by_id(self, question_id: UUID) -> Question | None:
        return next((q for q in self.added if q.id == question_id), None)


class FakeTagCatalogRepository:
    """get-or-create 的内存实现：同名（lower 键）复用同一 id。"""

    def __init__(self) -> None:
        self.by_key: dict[str, Tag] = {}

    async def get_or_create(self, tag: Tag) -> Tag:
        existing = self.by_key.get(tag.key)
        if existing is not None:
            return existing
        persisted = Tag(value=tag.value, id=uuid4())
        self.by_key[tag.key] = persisted
        return persisted

    async def list_all(self) -> list[Tag]:
        return list(self.by_key.values())


async def test_execute_persists_question_with_command_fields() -> None:
    repo = FakeQuestionRepository()
    use_case = AskQuestionUseCase(repo, FakeTagCatalogRepository())
    author_id = uuid4()

    result = await use_case.execute(
        AskQuestionCommand(title="  问题标题  ", body="问题正文", author_id=author_id)
    )

    assert len(repo.added) == 1
    assert repo.added[0] is result  # 落库的就是返回的聚合
    assert result.author_id == author_id
    assert result.title.value == "问题标题"  # 值对象已规范化
    assert result.body.value == "问题正文"
    assert result.tags == []  # 未带标签 → 空列表（1.3 功能域 5 L113-115）


async def test_execute_invalid_title_raises_and_persists_nothing() -> None:
    repo = FakeQuestionRepository()
    use_case = AskQuestionUseCase(repo, FakeTagCatalogRepository())

    with pytest.raises(ValueError):
        await use_case.execute(
            AskQuestionCommand(title="   ", body="正文", author_id=uuid4())
        )

    assert repo.added == []  # 校验失败不落库


async def test_execute_dedupes_case_insensitive_tags() -> None:
    """T02 同名归并：["SQL", "sql"] 去重为 1 个，且目录只建一行。"""
    repo = FakeQuestionRepository()
    tags_repo = FakeTagCatalogRepository()
    use_case = AskQuestionUseCase(repo, tags_repo)

    result = await use_case.execute(
        AskQuestionCommand(
            title="标题", body="正文", author_id=uuid4(), tags=("SQL", "sql")
        )
    )

    assert len(result.tags) == 1
    assert result.tags[0].value == "SQL"  # 首见规范名
    assert len(tags_repo.by_key) == 1  # 目录未重复建


async def test_execute_rejects_more_than_five_unique_tags() -> None:
    """Q03 去重后 >5 → ValueError（中文消息含"至多 5 个标签"）。"""
    repo = FakeQuestionRepository()
    use_case = AskQuestionUseCase(repo, FakeTagCatalogRepository())

    with pytest.raises(ValueError, match="至多 5 个标签"):
        await use_case.execute(
            AskQuestionCommand(
                title="标题",
                body="正文",
                author_id=uuid4(),
                tags=("a1", "b2", "c3", "d4", "e5", "f6"),
            )
        )

    assert repo.added == []  # 校验失败不落库


async def test_execute_rejects_illegal_tag_character() -> None:
    """白名单外字符（emoji）→ ValueError（字符串形 422 语义源）。"""
    repo = FakeQuestionRepository()
    use_case = AskQuestionUseCase(repo, FakeTagCatalogRepository())

    with pytest.raises(ValueError, match="不支持的字符"):
        await use_case.execute(
            AskQuestionCommand(
                title="标题", body="正文", author_id=uuid4(), tags=("数据库🔥",)
            )
        )
