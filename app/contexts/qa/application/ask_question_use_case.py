from __future__ import annotations

from app.contexts.qa.application.commands import AskQuestionCommand
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import QuestionRepository, TagCatalogRepository
from app.contexts.qa.domain.tag import TagCatalog


class AskQuestionUseCase:
    """提问用例：构造 Question 聚合（值对象即校验）并落库（US-Q01 + 迭代 4 Q03 打标）。

    US-Q04"发布后立即可见"为提交即读的自然结果，无独立逻辑。
    标签编排（aggregates.md 协作表"发布问题带标签"）：TagCatalog.resolve
    （白名单/去重/≤5）→ 目录 get-or-create（随用随建，T02）→ 聚合持 Tag 集合。
    全程单事务（get_session 边界），任一步失败整体回滚。
    """

    def __init__(
        self,
        repository: QuestionRepository,
        tag_repository: TagCatalogRepository,
    ) -> None:
        self._repository = repository
        self._tag_repository = tag_repository

    async def execute(self, command: AskQuestionCommand) -> Question:
        catalog = TagCatalog()
        tags = catalog.resolve(list(command.tags))
        persisted = [await self._tag_repository.get_or_create(t) for t in tags]
        question = Question.ask(
            title_value=command.title,
            body_value=command.body,
            author_id=command.author_id,
            tags=persisted,
        )
        await self._repository.add(question)
        return question
