from __future__ import annotations

from app.contexts.qa.application.commands import AskQuestionCommand
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import QuestionRepository


class AskQuestionUseCase:
    """提问用例：构造 Question 聚合（值对象即校验）并落库（US-Q01）。

    US-Q04"发布后立即可见"为提交即读的自然结果，无独立逻辑。
    """

    def __init__(self, repository: QuestionRepository) -> None:
        self._repository = repository

    async def execute(self, command: AskQuestionCommand) -> Question:
        question = Question.ask(
            title_value=command.title,
            body_value=command.body,
            author_id=command.author_id,
        )
        await self._repository.add(question)
        return question
