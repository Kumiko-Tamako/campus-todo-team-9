"""登录/刷新/退出/me 接口集成测试：httpx ASGI 传输 + 真 PostgreSQL + 真 Redis。

覆盖链路：注册 → 登录 → /me → refresh 轮换 → logout → 吊销后失效；
并发 refresh 用同一旧令牌仅一次成功（GETDEL 原子）。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import pytest

from app.main import create_app

pytestmark = pytest.mark.integration

BASE_URL = "http://test"


@pytest.fixture
async def client(redis_cleanup: None) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as c:
        yield c


def _register_payload() -> dict[str, str]:
    return {
        "role": "student",
        "email": f"{uuid.uuid4()}@stu.edu.cn",
        "password": "Passw0rd8",
        "student_id": str(uuid.uuid4().int)[:10],
    }


async def _register(client: httpx.AsyncClient) -> dict[str, Any]:
    payload = _register_payload()
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    return {"identifier": payload["student_id"], "password": payload["password"]}


async def _login(client: httpx.AsyncClient, identifier: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_full_flow(client: httpx.AsyncClient) -> None:
    creds = await _register(client)
    tokens = await _login(client, creds["identifier"], creds["password"])

    # 登录响应结构
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 900
    assert tokens["access_token"] != tokens["refresh_token"]

    # /me 带有效 Access
    me = await client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] is not None
    assert "password" not in me.json()

    # refresh 轮换：旧 Refresh 换新对
    # （Access 同秒签发内容可相同，关键断言 Refresh 必须不同——jti 保证）
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    new_pair = refreshed.json()
    assert new_pair["refresh_token"] != tokens["refresh_token"]

    # 旧 Refresh 已被原子消耗：再次使用 401
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401

    # 新 Refresh 仍可用
    refresh2 = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_pair["refresh_token"]}
    )
    assert refresh2.status_code == 200

    # logout 吊销当前 Refresh → 再 refresh 401
    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": refresh2.json()["refresh_token"]}
    )
    assert logout.status_code == 204
    after_logout = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh2.json()["refresh_token"]}
    )
    assert after_logout.status_code == 401


async def test_wrong_password_returns_401(client: httpx.AsyncClient) -> None:
    creds = await _register(client)
    resp = await client.post(
        "/api/v1/auth/login", json={"identifier": creds["identifier"], "password": "WrongPass1"}
    )
    assert resp.status_code == 401
    assert "access_token" not in resp.json()


async def test_unknown_identifier_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"identifier": "2025999999", "password": "Passw0rd8"}
    )
    assert resp.status_code == 401


async def test_sqli_identifier_returns_401(client: httpx.AsyncClient) -> None:
    """L-05 守护：SQL 注入串不含控制字符，穿透字符校验后由用例判 401（不被 422 误杀、不 500）。"""
    resp = await client.post(
        "/api/v1/auth/login", json={"identifier": "' OR '1'='1", "password": "x"}
    )
    assert resp.status_code == 401


async def test_me_without_token_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_tampered_token_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me", headers=_auth("tampered.token.value"))
    assert resp.status_code == 401


async def test_me_with_refresh_token_rejected(client: httpx.AsyncClient) -> None:
    """Refresh 令牌不能当 Access 用（typ 混用拒绝）。"""
    creds = await _register(client)
    tokens = await _login(client, creds["identifier"], creds["password"])
    resp = await client.get("/api/v1/auth/me", headers=_auth(tokens["refresh_token"]))
    assert resp.status_code == 401


async def test_logout_is_idempotent_204(client: httpx.AsyncClient) -> None:
    """无效令牌 logout 同样 204，不暴露令牌状态。"""
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": "garbage-token"})
    assert resp.status_code == 204


async def test_concurrent_refresh_only_one_succeeds(client: httpx.AsyncClient) -> None:
    """并发用同一 Refresh 令牌：GETDEL 原子保证仅一次成功。"""
    creds = await _register(client)
    tokens = await _login(client, creds["identifier"], creds["password"])
    refresh_token = tokens["refresh_token"]

    results = await asyncio.gather(
        *[
            client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
            for _ in range(5)
        ]
    )
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1
    assert codes.count(401) == 4


async def test_extra_fields_rejected(client: httpx.AsyncClient) -> None:
    """extra=forbid：登录请求带未定义字段 → 422。"""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "2025010101", "password": "Passw0rd8", "hacker": 1},
    )
    assert resp.status_code == 422
