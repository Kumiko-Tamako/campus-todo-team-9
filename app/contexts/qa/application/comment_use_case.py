"""评论用例：对问题/回答发表评论（US-C01）。"""

from __future__ import annotations

from app.contexts.qa.application.commands import CreateCommentCommand
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.errors import (
    AnswerNotFoundError,
    QuestionClosedError,
    QuestionNotFoundError,
)
from app.contexts.qa.domain.question import QuestionStatus
from app.contexts.qa.domain.repository import (
    AnswerRepository,
    CommentRepository,
    QuestionRepository,
)


class CreateCommentUseCase:
    """评论用例：目标存在检查（404）→ 关闭态拦截（409，迭代 5 落地 v3 裁定 #2）
    → Comment.write（Body 即校验，422）→ 落库。

    题评挂 Question、答评挂 Answer（aggregates.md L17）；
    已关闭禁评含题评与答评（答评经 answer.question_id 回溯父问题，全冻结口径）。
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
            question = await self._question_repository.get_by_id(command.target_id)
            if question is None:
                raise QuestionNotFoundError("问题不存在")
            if question.status is QuestionStatus.CLOSED:
                raise QuestionClosedError("已关闭的问题不可评论")
        else:
            answer = await self._answer_repository.get_by_id(command.target_id)
            if answer is None:
                raise AnswerNotFoundError("回答不存在")
            parent = await self._question_repository.get_by_id(answer.question_id)
            if parent is not None and parent.status is QuestionStatus.CLOSED:
                raise QuestionClosedError("已关闭的问题不可对回答评论")
        comment = Comment.write(
            target_type=command.target_type,
            target_id=command.target_id,
            author_id=command.author_id,
            body_value=command.body,
        )
        await self._comment_repository.add(comment)
        return comment