"""评论用例：对问题/回答发表评论（US-C01）。"""

from __future__ import annotations

from app.contexts.qa.application.commands import CreateCommentCommand
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.errors import AnswerNotFoundError, QuestionNotFoundError
from app.contexts.qa.domain.repository import (
    AnswerRepository,
    CommentRepository,
    QuestionRepository,
)


class CreateCommentUseCase:
    """评论用例：目标存在检查（404）→ Comment.write（Body 即校验，422）→ 落库。

    题评挂 Question、答评挂 Answer（aggregates.md L17）；
    "问题已关闭禁评"约束随 Q08 在迭代 5 落地（v3 裁定 #2），本迭代不检查。
    """

    def __init__(
        self,
        question_repository: QuestionRepository,
        answer_repository: AnswerRepository,
        comment_repository: CommentRepository,
    ) -> None:
        self._question_repository = question_repository
        self._answer_repository = answer_repository
        self._comment_repository = comment_repository

    async def execute(self, command: CreateCommentCommand) -> Comment:
        if command.target_type is CommentTarget.QUESTION:
            if await self._question_repository.get_by_id(command.target_id) is None:
                raise QuestionNotFoundError("问题不存在")
        else:
            if await self._answer_repository.get_by_id(command.target_id) is None:
                raise AnswerNotFoundError("回答不存在")
        comment = Comment.write(
            target_type=command.target_type,
            target_id=command.target_id,
            author_id=command.author_id,
            body_value=command.body,
        )
        await self._comment_repository.add(comment)
        return comment
