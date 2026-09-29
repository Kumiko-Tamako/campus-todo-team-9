"""编辑问题用例：提问者编辑自己的问题（US-Q08；裁定 D6 仅标题+正文）。"""

from __future__ import annotations

from app.contexts.qa.application.commands import EditQuestionCommand
from app.contexts.qa.domain.errors import NotQuestionAuthorError, QuestionNotFoundError
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import QuestionRepository


class EditQuestionUseCase:
    """编辑用例：问题不存在→404；非提问者→403；已关闭→409（全冻结裁定）；
    标题/正文校验失败→422（ValueError，由路由映射）。

    PATCH 部分更新：命令缺省侧沿用既有值合并后再入域方法（标签不可编辑，D6）。
    """

    def __init__(self, question_repository: QuestionRepository) -> None:
        self._question_repository = question_repository

    async def execute(self, command: EditQuestionCommand) -> Question:
        question = await self._question_repository.get_by_id(command.question_id)
        if question is None:
            raise QuestionNotFoundError("问题不存在")
        if question.author_id != command.actor_id:
            raise NotQuestionAuthorError("仅提问者可编辑问题")
        title_value = command.title if command.title is not None else question.title.value
        body_value = command.body if command.body is not None else question.body.value
        question.edit_title_body(title_value=title_value, body_value=body_value)
        await self._question_repository.update(question)
        return question