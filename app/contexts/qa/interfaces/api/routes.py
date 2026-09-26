from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.deps import CurrentUser
from app.contexts.qa.application.accept_use_case import AcceptAnswerUseCase
from app.contexts.qa.application.answer_use_case import PostAnswerUseCase
from app.contexts.qa.application.ask_question_use_case import AskQuestionUseCase
from app.contexts.qa.application.commands import (
    AcceptAnswerCommand,
    AskQuestionCommand,
    CreateCommentCommand,
    PostAnswerCommand,
    VoteOnCommand,
)
from app.contexts.qa.application.comment_use_case import CreateCommentUseCase
from app.contexts.qa.application.get_question_use_case import GetQuestionUseCase
from app.contexts.qa.application.list_questions_use_case import ListQuestionsUseCase
from app.contexts.qa.application.queries import GetQuestionQuery, ListQuestionsQuery
from app.contexts.qa.application.vote_use_case import VoteOnUseCase
from app.contexts.qa.domain.comment import Comment, CommentTarget
from app.contexts.qa.domain.errors import (
    AlreadyVotedError,
    AnswerAlreadyAcceptedError,
    AnswerNotFoundError,
    NotQuestionAuthorError,
    QuestionNotFoundError,
)
from app.contexts.qa.domain.repository import QuestionSort
from app.contexts.qa.domain.vote import VoteDirection, VoteTarget
from app.contexts.qa.infrastructure.repository import (
    SqlAlchemyAnswerRepository,
    SqlAlchemyCommentRepository,
    SqlAlchemyQuestionRepository,
    SqlAlchemyVoteRepository,
)
from app.contexts.qa.interfaces.api.schemas import (
    AnswerResponse,
    AskQuestionRequest,
    CommentRequest,
    CommentResponse,
    PostAnswerRequest,
    QuestionDetailResponse,
    QuestionListItem,
    QuestionListResponse,
    QuestionResponse,
    VoteRequest,
)
from app.shared.engine import get_session

router = APIRouter(prefix="/api/v1/questions", tags=["questions"])
answers_router = APIRouter(prefix="/api/v1/answers", tags=["answers"])


@router.post(
    "",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="发布问题（登录用户）",
)
async def ask_question(
    payload: AskQuestionRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> QuestionResponse:
    use_case = AskQuestionUseCase(SqlAlchemyQuestionRepository(session))
    try:
        question = await use_case.execute(
            AskQuestionCommand(
                title=payload.title,
                body=payload.body,
                author_id=user.id,  # 作者只取令牌中的当前用户，绝不取自请求体
            )
        )
    except ValueError as exc:  # Title/Body 值对象兜底校验（schema 已拦大部分形态）
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return QuestionResponse(
        id=question.id,
        title=question.title.value,
        body=question.body.value,
        author_id=question.author_id,
        created_at=question.created_at,
    )


@router.get(
    "",
    response_model=QuestionListResponse,
    summary="问题列表（访客可用，默认按发布时间新→旧，可按净票数排序）",
)
async def list_questions(
    page: int = Query(default=1, ge=1, description="页码，从 1 起"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数，上限 100（S-05）"),
    sort: QuestionSort = Query(
        default=QuestionSort.LATEST,
        description="排序：latest=最新（默认）；votes=净票数高→低（US-Q02 迭代 2）",
    ),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> QuestionListResponse:
    # sort 为枚举：非法值（含注入串）在参数校验即 422，不进 SQL（S-07 迭代 2 收紧）
    use_case = ListQuestionsUseCase(SqlAlchemyQuestionRepository(session))
    result = await use_case.execute(
        ListQuestionsQuery(page=page, page_size=page_size, sort=sort)
    )
    return QuestionListResponse(
        items=[
            QuestionListItem(
                id=q.id,
                title=q.title.value,
                author_id=q.author_id,
                created_at=q.created_at,
            )
            for q in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.get(
    "/{question_id}",
    response_model=QuestionDetailResponse,
    summary="问题详情（访客可用，answers 按 D2 排序）",
)
async def get_question(
    question_id: UUID,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> QuestionDetailResponse:
    use_case = GetQuestionUseCase(
        SqlAlchemyQuestionRepository(session),
        SqlAlchemyAnswerRepository(session),
        SqlAlchemyCommentRepository(session),
    )
    view = await use_case.execute(GetQuestionQuery(question_id=question_id))
    if view is None:
        # S-10：只回业务语义，不泄露内部信息
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问题不存在")
    return QuestionDetailResponse(
        id=view.question.id,
        title=view.question.title.value,
        body=view.question.body.value,
        author_id=view.question.author_id,
        created_at=view.question.created_at,
        accepted_answer_id=view.question.accepted_answer_id,
        tags=[],
        answers=[
            AnswerResponse(
                id=a.id,
                body=a.body.value,
                author_id=a.author_id,
                created_at=a.created_at,
                votes=a.votes_count,
                is_accepted=a.is_accepted,
                comments=[_comment_response(c) for c in view.answer_comments.get(str(a.id), [])],
            )
            for a in view.answers
        ],
        comments=[_comment_response(c) for c in view.question_comments],
    )


def _comment_response(comment: Comment) -> CommentResponse:
    return CommentResponse(
        id=comment.id,
        body=comment.body.value,
        author_id=comment.author_id,
        created_at=comment.created_at,
    )


@router.post(
    "/{question_id}/answers",
    response_model=AnswerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="发布回答（登录用户，US-A01）",
)
async def post_answer(
    question_id: UUID,
    payload: PostAnswerRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> AnswerResponse:
    use_case = PostAnswerUseCase(
        SqlAlchemyQuestionRepository(session), SqlAlchemyAnswerRepository(session)
    )
    try:
        answer = await use_case.execute(
            PostAnswerCommand(
                question_id=question_id,
                body=payload.body,
                author_id=user.id,  # 作者只取令牌，绝不取自请求体
            )
        )
    except QuestionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:  # Body 值对象兜底校验
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return AnswerResponse(
        id=answer.id,
        body=answer.body.value,
        author_id=answer.author_id,
        created_at=answer.created_at,
        votes=0,  # 新回答无票
        is_accepted=answer.is_accepted,
    )


async def _vote(
    target_type: VoteTarget,
    target_id: UUID,
    payload: VoteRequest,
    user_id: UUID,
    session: AsyncSession,
) -> Response:
    """两个投票端点共用：成功 204；目标不存在 404；重复票（含改票）409。"""
    use_case = VoteOnUseCase(
        SqlAlchemyQuestionRepository(session),
        SqlAlchemyAnswerRepository(session),
        SqlAlchemyVoteRepository(session),
    )
    try:
        await use_case.execute(
            VoteOnCommand(
                target_type=target_type,
                target_id=target_id,
                direction=VoteDirection(payload.direction),
                user_id=user_id,
            )
        )
    except (QuestionNotFoundError, AnswerNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AlreadyVotedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{question_id}/vote",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="对问题投票（登录用户，US-V01；重复票/改票 409）",
)
async def vote_question(
    question_id: UUID,
    payload: VoteRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    return await _vote(VoteTarget.QUESTION, question_id, payload, user.id, session)


@router.post(
    "/{question_id}/answers/{answer_id}/vote",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="对回答投票（登录用户，US-V01；重复票/改票 409）",
)
async def vote_answer(
    question_id: UUID,
    answer_id: UUID,
    payload: VoteRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    # 路径嵌套仅为可读性；回答存在性由 answer_id 定位（question_id 不参与查询）
    return await _vote(VoteTarget.ANSWER, answer_id, payload, user.id, session)


async def _create_comment(
    target_type: CommentTarget,
    target_id: UUID,
    payload: CommentRequest,
    user_id: UUID,
    session: AsyncSession,
) -> CommentResponse:
    """题评/答评端点共用：成功 201 + 白名单；目标不存在 404；正文兜底 422。"""
    use_case = CreateCommentUseCase(
        SqlAlchemyQuestionRepository(session),
        SqlAlchemyAnswerRepository(session),
        SqlAlchemyCommentRepository(session),
    )
    try:
        comment = await use_case.execute(
            CreateCommentCommand(
                target_type=target_type,
                target_id=target_id,
                body=payload.body,
                author_id=user_id,  # 作者只取令牌，绝不取自请求体
            )
        )
    except (QuestionNotFoundError, AnswerNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:  # Body 值对象兜底校验
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _comment_response(comment)


@router.post(
    "/{question_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="对问题发表评论（登录用户，US-C01）",
)
async def comment_question(
    question_id: UUID,
    payload: CommentRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> CommentResponse:
    return await _create_comment(CommentTarget.QUESTION, question_id, payload, user.id, session)


@answers_router.post(
    "/{answer_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="对回答发表评论（登录用户，US-C01）",
)
async def comment_answer(
    answer_id: UUID,
    payload: CommentRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> CommentResponse:
    return await _create_comment(CommentTarget.ANSWER, answer_id, payload, user.id, session)


@answers_router.post(
    "/{answer_id}/accept",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="采纳最佳答案（仅提问者，US-V03；非提问者 403 / 重复采纳 409）",
)
async def accept_answer(
    answer_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    use_case = AcceptAnswerUseCase(
        SqlAlchemyQuestionRepository(session), SqlAlchemyAnswerRepository(session)
    )
    try:
        await use_case.execute(AcceptAnswerCommand(answer_id=answer_id, actor_id=user.id))
    except AnswerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NotQuestionAuthorError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AnswerAlreadyAcceptedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
