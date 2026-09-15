from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.deps import CurrentUser
from app.contexts.qa.application.ask_question_use_case import AskQuestionUseCase
from app.contexts.qa.application.commands import AskQuestionCommand
from app.contexts.qa.application.get_question_use_case import GetQuestionUseCase
from app.contexts.qa.application.list_questions_use_case import ListQuestionsUseCase
from app.contexts.qa.application.queries import GetQuestionQuery, ListQuestionsQuery
from app.contexts.qa.infrastructure.repository import SqlAlchemyQuestionRepository
from app.contexts.qa.interfaces.api.schemas import (
    AskQuestionRequest,
    QuestionDetailResponse,
    QuestionListItem,
    QuestionListResponse,
    QuestionResponse,
)
from app.shared.engine import get_session

router = APIRouter(prefix="/api/v1/questions", tags=["questions"])


@router.post(
    "",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="发布问题（登录用户）",
)
async def ask_question(
    payload: AskQuestionRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
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
    summary="问题列表（访客可用，按发布时间新→旧）",
)
async def list_questions(
    page: int = Query(default=1, ge=1, description="页码，从 1 起"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数，上限 100（S-05）"),
    session: AsyncSession = Depends(get_session),
) -> QuestionListResponse:
    use_case = ListQuestionsUseCase(SqlAlchemyQuestionRepository(session))
    result = await use_case.execute(ListQuestionsQuery(page=page, page_size=page_size))
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
    summary="问题详情（访客可用）",
)
async def get_question(
    question_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> QuestionDetailResponse:
    use_case = GetQuestionUseCase(SqlAlchemyQuestionRepository(session))
    question = await use_case.execute(GetQuestionQuery(question_id=question_id))
    if question is None:
        # S-10：只回业务语义，不泄露内部信息
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问题不存在")
    return QuestionDetailResponse(
        id=question.id,
        title=question.title.value,
        body=question.body.value,
        author_id=question.author_id,
        created_at=question.created_at,
        tags=[],
        answers=[],
    )
