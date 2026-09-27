"""全局异常处理器（修复暴力测试 P-03/P-04，兜底 P-01/P-02）。

- request_validation_exception_handler：422 错误项只回 type/loc/msg，不回显 input。
  FastAPI 默认处理器回显非法输入：lone surrogate 回显体无法 UTF-8 编码
  （UnicodeEncodeError）、深度嵌套输入使 jsonable_encoder 递归爆栈
  （RecursionError）——本应 422 的请求被打成 500。
- sqlalchemy_error_handler：未被路由捕获的数据库错误统一回 400，
  响应体不含驱动/栈信息，异常详情仅写服务端日志。
- db_unavailable_handler：数据库暂不可达（asyncpg 裸连接异常 / 池排队超时）→ 503。
- dbapi_error_handler：DBAPIError 分流——业务/代码类（IntegrityError/DataError/
  ProgrammingError）沿用 400 兜底语义，其余（连接类/泛型）落 503。
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, DBAPIError, IntegrityError, ProgrammingError

logger = logging.getLogger(__name__)


async def request_validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """422：只回错误类型/位置/信息，绝不回显原始输入（防编码崩溃与递归爆栈）。"""
    assert isinstance(exc, RequestValidationError)  # 注册时绑定的异常类，必然成立
    safe_errors: list[dict[str, object]] = [
        {
            "type": str(error.get("type", "validation_error")),
            "loc": list(error.get("loc", ())),
            "msg": str(error.get("msg", "请求参数校验失败")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": safe_errors})


async def sqlalchemy_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """数据库错误兜底：400 + 通用文案，异常详情仅入服务端日志，不回传客户端。"""
    logger.warning("未被路由捕获的数据库错误", exc_info=exc)
    return JSONResponse(
        status_code=400,
        content={"detail": "请求数据无法被数据库接受，请检查输入内容"},
    )


async def db_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """数据库暂时不可达：503 + 通用文案，异常详情仅入服务端日志。"""
    logger.warning("数据库暂时不可达", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "服务暂时不可用，请稍后重试"},
    )


async def dbapi_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """DBAPIError 分流：业务/代码错误沿用 400 兜底；连接类与泛型落 503。"""
    assert isinstance(exc, DBAPIError)  # 注册时绑定的异常类，必然成立
    if isinstance(exc, (IntegrityError, DataError, ProgrammingError)):
        return await sqlalchemy_error_handler(request, exc)
    if _asyncpg_sqlstate_in(exc, ("22",)):
        # 服务端数据类错误（22xxx，如 22001 截断）：恢复设计的 DataError→400。
        # asyncpg 的该族经方言映射落 sqlalchemy InterfaceError（sqlalchemy 侧
        # 无法与连接类 InterfaceError 区分），经 orig.__cause__ 的 SQLSTATE 识别
        # （第八路观察点 1：曾是死分支）。
        return await sqlalchemy_error_handler(request, exc)
    return await db_unavailable_handler(request, exc)


def _asyncpg_sqlstate_in(exc: DBAPIError, prefixes: tuple[str, ...]) -> bool:
    """方言翻译后 orig.__cause__ 链上挂着 asyncpg 服务端原错误（含 sqlstate）。"""
    cause = getattr(getattr(exc, "orig", None), "__cause__", None)
    sqlstate = getattr(cause, "sqlstate", None)
    return isinstance(sqlstate, str) and sqlstate.startswith(prefixes)
