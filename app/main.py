from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import get_settings
from app.contexts.identity.interfaces.api.routes import router as auth_router
from app.contexts.qa.interfaces.api.routes import router as qa_router
from app.shared.body_limit import BodyLimitMiddleware
from app.shared.exception_handlers import (
    request_validation_exception_handler,
    sqlalchemy_error_handler,
)


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.debug)
    application.add_middleware(BodyLimitMiddleware)
    # 422 不回显 input（治 surrogate/递归炸弹 500）；数据库错误统一 400 兜底
    application.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    application.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    application.include_router(auth_router)
    application.include_router(qa_router)

    @application.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
