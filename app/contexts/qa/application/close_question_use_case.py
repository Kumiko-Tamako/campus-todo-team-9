"""关闭问题用例：提问者关闭自己的问题（US-Q08；V02 关闭禁投的触发动作）。"""

from __future__ import annotations

from app.contexts.qa.application.commands import CloseQuestionCommand
from app.contexts.qa.domain.errors import NotQuestionAuthorError, QuestionNotFoundError
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import QuestionRepository


class CloseQuestionUseCase:
    """关闭用例：问题不存在→404；非提问者→403；重复关闭/已采纳→409（域内不变式）。

    关闭为终态（2026-09-29 裁定全冻结，无重开故事）：此后编辑/新增回答/投票/
    评论/采纳一律 409；成功后 Question.close() 追加 QuestionClosed 事件（无订阅者照发）。
    """

    def __init__(self, question_repository: QuestionRepository) -> None:
        self._question_repository = question_repository

    async def execute(self, command: CloseQuestionCommand) -> Question:
        question = await self._question_repository.get_by_id(command.question_id)
        if question is None:
            raise QuestionNotFoundError("问题不存在")
        if question.author_id != command.actor_id:
            raise NotQuestionAuthorError("仅提问者可关闭问题")
        question.close()
        await self._question_repository.update(question)
        return question