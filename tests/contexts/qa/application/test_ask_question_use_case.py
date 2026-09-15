"""AskQuestionUseCase 单元测试：fake 仓储，不连库（进 CI）。"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.contexts.qa.application.ask_question_use_case import AskQuestionUseCase
from app.contexts.qa.application.commands import AskQuestionCommand
from app.contexts.qa.domain.question import Question


class FakeQuestionRepository:
    """记录 add 调用的内存仓储。"""

    def __init__(self) -> None:
        self.added: list[Question] = []

    async def add(self, question: Question) -> None:
        self.added.append(question)

    async def get_by_id(self, question_id: UUID) -> Question | None:
        return next((q for q in self.added if q.id == question_id), None)


async def test_execute_persists_question_with_command_fields() -> None:
    repo = FakeQuestionRepository()
    use_case = AskQuestionUseCase(repo)
    author_id = uuid4()

    result = await use_case.execute(
        AskQuestionCommand(title="  问题标题  ", body="问题正文", author_id=author_id)
    )

    assert len(repo.added) == 1
    assert repo.added[0] is result  # 落库的就是返回的聚合
    assert result.author_id == author_id
    assert result.title.value == "问题标题"  # 值对象已规范化
    assert result.body.value == "问题正文"


async def test_execute_invalid_title_raises_and_persists_nothing() -> None:
    repo = FakeQuestionRepository()
    use_case = AskQuestionUseCase(repo)

    with pytest.raises(ValueError):
        await use_case.execute(
            AskQuestionCommand(title="   ", body="正文", author_id=uuid4())
        )

    assert repo.added == []  # 校验失败不落库
