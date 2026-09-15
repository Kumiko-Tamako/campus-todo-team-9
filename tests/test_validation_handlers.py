"""全局校验异常处理器与边界字符校验的接口回归测试（不连库，进 CI）。

覆盖暴力测试 P-01~P-04 在公开端点（register/login）的形态：
- NUL / lone surrogate / 递归炸弹一律 422，绝不 500；
- 422 响应错误项只含 type/loc/msg，绝不回显 input（修1 的核心断言）；
- 响应体不含 traceback / 驱动名等栈泄露。

这些请求全部在 schema 校验阶段被拒，不进入路由、不触碰数据库，
因此 CI（无 PostgreSQL/Redis 服务）同样可跑。
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import ASGITransport, AsyncClient

from app.main import create_app

_REGISTER = "/api/v1/auth/register"
_LOGIN = "/api/v1/auth/login"
_LEAK_KEYWORDS = ("traceback", 'file "', "psycopg", "asyncpg", "sqlalchemy")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


def _register_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "student",
        "email": f"{uuid.uuid4().hex[:10]}@stu.edu.cn",
        "password": "Passw0rd8",
        "student_id": str(uuid.uuid4().int)[:10],
    }
    payload.update(overrides)
    return payload


def _assert_safe_422(resp_text: str, resp_json: Any) -> None:
    """422 响应形状：detail 为错误项列表，每项恰好 type/loc/msg，无 input 回显。"""
    lowered = resp_text.lower()
    assert not any(k in lowered for k in _LEAK_KEYWORDS)
    assert '"input"' not in lowered
    detail = resp_json["detail"]
    assert isinstance(detail, list) and detail
    for item in detail:
        assert set(item.keys()) == {"type", "loc", "msg"}


async def test_register_nul_email_returns_422() -> None:
    async with _client() as client:
        resp = await client.post(_REGISTER, json=_register_payload(email="n\x00x@stu.edu.cn"))
    assert resp.status_code == 422, resp.text
    _assert_safe_422(resp.text, resp.json())


async def test_register_lone_surrogate_email_returns_422() -> None:
    # 旧行为：Pydantic 拦截后默认 handler 回显含 surrogate 的 input →
    # Starlette UTF-8 编码 UnicodeEncodeError → 500
    raw = (
        b'{"role":"student","student_id":"1234567890",'
        b'"email":"\\ud800@x.cn","password":"Passw0rd8"}'
    )
    async with _client() as client:
        resp = await client.post(
            _REGISTER, content=raw, headers={"content-type": "application/json"}
        )
    assert resp.status_code == 422, resp.text
    _assert_safe_422(resp.text, resp.json())


async def test_register_recursive_bomb_returns_422() -> None:
    # 旧行为：json.loads 成功、Pydantic 报错，但 jsonable_encoder 递归
    # 遍历 2000 层回显 input → RecursionError → 500
    bomb = b'{"a":' * 2000 + b"1" + b"}" * 2000
    async with _client() as client:
        resp = await client.post(
            _REGISTER, content=bomb, headers={"content-type": "application/json"}
        )
    assert resp.status_code == 422, resp.text
    _assert_safe_422(resp.text, resp.json())


async def test_login_nul_identifier_returns_422() -> None:
    async with _client() as client:
        resp = await client.post(
            _LOGIN, json={"identifier": "a\x00b", "password": "Passw0rd8"}
        )
    assert resp.status_code == 422, resp.text
    _assert_safe_422(resp.text, resp.json())


async def test_missing_fields_422_does_not_echo_input() -> None:
    async with _client() as client:
        resp = await client.post(_REGISTER, json={})
    assert resp.status_code == 422, resp.text
    _assert_safe_422(resp.text, resp.json())
