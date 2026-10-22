"""登录失败锁定集成测试（US-L04，迭代 5）：httpx ASGI + 真 PostgreSQL + 真 Redis。

覆盖：前 5 次失败 401、第 6 次起 423；锁定期内正确密码同样 423；
成功登录清零；窗口 TTL 实证；全 identifier 统一计数（不存在的账号同样计数锁定）；
键清除（等价窗口过期）后恢复登录。
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.contexts.identity.application.ports import (
    LOGIN_FAILURE_THRESHOLD,
    LOGIN_LOCKOUT_WINDOW,
)
from app.main import create_app
from app.shared.redis import get_redis

pytestmark = pytest.mark.integration

BASE_URL = "http://test"


@pytest.fixture
async def client(redis_cleanup: None) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as c:
        yield c


async def _register(client: httpx.AsyncClient) -> dict[str, str]:
    payload = {
        "role": "student",
        "email": f"{uuid.uuid4()}@stu.edu.cn",
        "password": "Passw0rd8",
        "student_id": str(uuid.uuid4().int)[:10],
    }
    reg = await client.post("/api/v1/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    return payload


async def _login(client: httpx.AsyncClient, identifier: str, password: str) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )


def _key(identifier: str) -> str:
    return f"login:fail:{identifier}"


async def test_lockout_after_threshold_then_correct_password_still_423(
    client: httpx.AsyncClient,
) -> None:
    payload = await _register(client)
    sid = payload["student_id"]

    for _ in range(LOGIN_FAILURE_THRESHOLD):
        r = await _login(client, sid, "WrongPass1")
        assert r.status_code == 401, r.text

    r = await _login(client, sid, "WrongPass1")
    assert r.status_code == 423  # 第 6 次起锁定（超阈值）
    r = await _login(client, sid, payload["password"])
    assert r.status_code == 423  # 锁定期内正确密码同样被拒

    ttl = await get_redis().ttl(_key(sid))
    assert 0 < ttl <= int(LOGIN_LOCKOUT_WINDOW.total_seconds())  # 窗口 TTL 存在且不超界


async def test_unlock_after_key_cleared_restores_login(client: httpx.AsyncClient) -> None:
    """等价窗口过期：键清除后同一 identifier 恢复登录（TTL 过期语义实证）。"""
    payload = await _register(client)
    sid = payload["student_id"]
    for _ in range(LOGIN_FAILURE_THRESHOLD + 1):
        await _login(client, sid, "WrongPass1")
    assert (await _login(client, sid, payload["password"])).status_code == 423

    await get_redis().delete(_key(sid))  # 模拟 15 分钟窗口到期

    r = await _login(client, sid, payload["password"])
    assert r.status_code == 200, r.text
    assert (await get_redis().exists(_key(sid))) == 0  # 成功登录即清零


async def test_success_clears_counter_so_filter_restarts_fresh(
    client: httpx.AsyncClient,
) -> None:
    payload = await _register(client)
    sid = payload["student_id"]

    for _ in range(3):
        assert (await _login(client, sid, "WrongPass1")).status_code == 401
    assert (await _login(client, sid, payload["password"])).status_code == 200  # 清零
    assert (await get_redis().exists(_key(sid))) == 0

    for _ in range(LOGIN_FAILURE_THRESHOLD - 1):  # 清零后重新累计：前 4 次 401
        assert (await _login(client, sid, "WrongPass1")).status_code == 401
    assert (await _login(client, sid, "WrongPass1")).status_code == 401  # 第 5 次失败本身仍 401
    assert (await _login(client, sid, "WrongPass1")).status_code == 423  # 第 6 次起锁定


async def test_unknown_identifier_also_counted(client: httpx.AsyncClient) -> None:
    """全 identifier 统一计数（裁定 D4）：不存在的账号失败同样累计、同样锁定。"""
    ghost = str(uuid.uuid4().int)[:10]
    for _ in range(LOGIN_FAILURE_THRESHOLD):
        assert (await _login(client, ghost, "WrongPass1")).status_code == 401
    assert (await _login(client, ghost, "WrongPass1")).status_code == 423


async def test_other_identifiers_unaffected(client: httpx.AsyncClient) -> None:
    locked_user = await _register(client)
    healthy_user = await _register(client)
    for _ in range(LOGIN_FAILURE_THRESHOLD):
        await _login(client, locked_user["student_id"], "WrongPass1")
    assert (await _login(client, locked_user["student_id"], "WrongPass1")).status_code == 423

    assert (
        await _login(client, healthy_user["student_id"], healthy_user["password"])
    ).status_code == 200