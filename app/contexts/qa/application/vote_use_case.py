"""投票用例：对问题/回答投一票（US-V01，D1 同步事务写库）。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.contexts.qa.application.commands import VoteOnCommand
from app.contexts.qa.domain.errors import (
    AlreadyVotedError,
    AnswerNotFoundError,
    QuestionNotFoundError,
)
from app.contexts.qa.domain.repository import (
    AnswerRepository,
    QuestionRepository,
    VoteRepository,
)
from app.contexts.qa.domain.vote import Vote, VoteCast, VoteTarget


@dataclass(frozen=True, slots=True)
class VoteOutcome:
    """投票结果：落库的票 + 随行为发出的 VoteCast 事件。

    迭代 2 无事件总线，事件照发留位（与 QuestionPublished 同模式）；
    分支 4 接入 Celery 消费方后由总线投递。
    """

    vote: Vote
    event: VoteCast


class VoteOnUseCase:
    """投票用例：定位目标（不存在→404）→ 一人一票事前检查（已有票→409）→ 落票并发事件。

    并发窗口内的重复票由库级复合唯一索引兜底（IntegrityError→409，步骤 3 实现）；
    不可改票（v3 裁定 #5）：再次投票一律 AlreadyVotedError。
    """

    def __init__(
        self,
        question_repository: QuestionRepository,
        answer_repository: AnswerRepository,
        vote_repository: VoteRepository,
    ) -> None:
        self._question_repository = question_repository
        self._answer_repository = answer_repository
        self._vote_repository = vote_repository

    async def _target_author(self, target_type: VoteTarget, target_id: UUID) -> UUID:
        """定位目标并返回作者（不存在→404）。

        v3.1 D-A'(i)：本就加载完整聚合，顺手提取 author_id 进事件载荷
        （worker 零查库），替代原 _target_exists 的"只判存在"。
        """
        if target_type is VoteTarget.QUESTION:
            question = await self._question_repository.get_by_id(target_id)
            if question is None:
                raise QuestionNotFoundError("问题不存在")
            return question.author_id
        answer = await self._answer_repository.get_by_id(target_id)
        if answer is None:
            raise AnswerNotFoundError("回答不存在")
        return answer.author_id

    async def execute(self, command: VoteOnCommand) -> VoteOutcome:
        target_author_id = await self._target_author(command.target_type, command.target_id)
        existing = await self._vote_repository.find_by_user_target(
            command.user_id, command.target_type, command.target_id
        )
        if existing is not None:
            raise AlreadyVotedError("已对该对象投过票")
        vote = Vote.cast(
            user_id=command.user_id,
            target_type=command.target_type,
            target_id=command.target_id,
            direction=command.direction,
        )
        await self._vote_repository.add(vote)
        return VoteOutcome(
            vote=vote, event=vote.cast_event(target_author_id=target_author_id)
        )
