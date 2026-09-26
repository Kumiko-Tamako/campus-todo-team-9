"""详情用例：按 ID 读取问题 + 回答区/评论区组装（US-Q06/A05/C01/V03 展示）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.contexts.qa.application.queries import GetQuestionQuery
from app.contexts.qa.domain.answer import Answer
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.question import Question
from app.contexts.qa.domain.repository import (
    AnswerRepository,
    CommentRepository,
    QuestionRepository,
)


@dataclass(frozen=True, slots=True)
class QuestionDetailView:
    """详情读模型：问题聚合 + 按 D2 排序的回答列表（净票口径，v3 裁定 #1）
    + 题评列表 + 各答答评映射（1.3 功能域 9"评论出现在评论列表"的读取路径）。"""

    question: Question
    answers: list[Answer] = field(default_factory=list)
    question_comments: list[Comment] = field(default_factory=list)
    answer_comments: dict[str, list[Comment]] = field(default_factory=dict)


class GetQuestionUseCase:
    """详情读取：不存在返回 None（路由层转 404，不泄露内部信息）。

    answers 区由 AnswerRepository.list_by_question 提供（排序在仓储 SQL 侧完成：
    已采纳恒最前 > 净票数降序 > 时间正序 > id tiebreaker）；
    评论按时间正序（1.3 功能域 9），题评/答评分组返回。
    """

    def __init__(
        self,
        repository: QuestionRepository,
        answer_repository: AnswerRepository,
        comment_repository: CommentRepository,
    ) -> None:
        self._repository = repository
        self._answer_repository = answer_repository
        self._comment_repository = comment_repository

    async def execute(self, query: GetQuestionQuery) -> QuestionDetailView | None:
        question = await self._repository.get_by_id(query.question_id)
        if question is None:
            return None
        answers = await self._answer_repository.list_by_question(question.id)
        question_comments = await self._comment_repository.list_by_target(
            CommentTarget.QUESTION, question.id
        )
        answer_comments = {
            str(a.id): await self._comment_repository.list_by_target(CommentTarget.ANSWER, a.id)
            for a in answers
        }
        return QuestionDetailView(
            question=question,
            answers=answers,
            question_comments=question_comments,
            answer_comments=answer_comments,
        )
