"""详情用例：按 ID 读取问题（US-Q06，访客可用）。"""

from __future__ import annotations

from app.contexts.qa.application.queries import GetQuestionQuery
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import QuestionRepository


class GetQuestionUseCase:
    """详情读取：不存在返回 None（路由层转 404，不泄露内部信息）。"""

    def __init__(self, repository: QuestionRepository) -> None:
        self._repository = repository

    async def execute(self, query: GetQuestionQuery) -> Question | None:
        return await self._repository.get_by_id(query.question_id)
