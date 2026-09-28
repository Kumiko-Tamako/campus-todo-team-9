"""声誉接口集成测试：httpx ASGI + 真 PostgreSQL + Celery eager（端到端记账）。

覆盖（Gherkin 功能域 11 + v3.1 裁定）：
- 投票/采纳 → eager 任务同步记账 → GET 本人声誉（Gherkin 场景 1/2/3）
- 自投不计分；重复票 409 不加行；重复采纳 409 仅一次
- GET 仅本人（他人 403 / 未登录 401）；空账 total=0
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from app.contexts.reputation.infrastructure.celery_app import celery_app
from app.main import create_app

pytestmark = pytest.mark.integration

BASE_URL = "http://test"


@pytest.fixture
def celery_eager() -> Any:
    """eager 模式：BackgroundTasks 内 .delay 同步执行（不触 broker，仍走真实任务体）。"""
    celery_app.conf.task_always_eager = True
    yield celery_app
    celery_app.conf.task_always_eager = False


@pytest.fixture
async def client(redis_cleanup: None, celery_eager: Any) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as c:
        yield c


async def _register_and_login(client: httpx.AsyncClient) -> dict[str, Any]:
    payload = {
        "role": "student",
        "email": f"{uuid.uuid4()}@stu.edu.cn",
        "password": "Passw0rd8",
        "student_id": str(uuid.uuid4().int)[:10],
    }
    reg = await client.post("/api/v1/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"identifier": payload["student_id"], "password": payload["password"]},
    )
    assert login.status_code == 200, login.text
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert me.status_code == 200, me.text
    return {"token": login.json()["access_token"], "id": me.json()["id"]}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_vote_and_accept_ledger_end_to_end(client: httpx.AsyncClient) -> None:
    """Gherkin 场景 1+2：B 赞 A 的回答 → A？不——赞记给作者；A 采纳 B 回答 → B +15。

    布局：A 提问，B 回答；B 赞 A 的问题（A +5）；A 赞 B 的回答（B +10）并采纳
    （B +15）。GET 验证双方总值与倒序流水（场景 3）。
    """
    author = await _register_and_login(client)  # A：提问者
    responder = await _register_and_login(client)  # B：回答者

    q = await client.post(
        "/api/v1/questions",
        json={"title": f"声誉测试 {uuid.uuid4().hex[:6]}", "body": "正文"},
        headers=_auth(author["token"]),
    )
    assert q.status_code == 201, q.text
    question_id = q.json()["id"]

    a = await client.post(
        f"/api/v1/questions/{question_id}/answers",
        json={"body": "回答正文"},
        headers=_auth(responder["token"]),
    )
    assert a.status_code == 201, a.text
    answer_id = a.json()["id"]

    # B 赞 A 的问题 → A +5
    assert (
        await client.post(
            f"/api/v1/questions/{question_id}/vote",
            json={"direction": "up"},
            headers=_auth(responder["token"]),
        )
    ).status_code == 204
    # A 赞 B 的回答 → B +10
    assert (
        await client.post(
            f"/api/v1/questions/{question_id}/answers/{answer_id}/vote",
            json={"direction": "up"},
            headers=_auth(author["token"]),
        )
    ).status_code == 204
    # A 采纳 → B +15
    assert (
        await client.post(
            f"/api/v1/answers/{answer_id}/accept", headers=_auth(author["token"])
        )
    ).status_code == 204

    rep_a = await client.get(
        f"/api/v1/users/{author['id']}/reputation", headers=_auth(author["token"])
    )
    assert rep_a.status_code == 200, rep_a.text
    body_a = rep_a.json()
    assert body_a["total"] == 5
    assert [e["reason"] for e in body_a["entries"]] == ["问题被赞"]

    rep_b = await client.get(
        f"/api/v1/users/{responder['id']}/reputation", headers=_auth(responder["token"])
    )
    assert rep_b.status_code == 200, rep_b.text
    body_b = rep_b.json()
    assert body_b["total"] == 25  # +10 赞 +15 采纳
    # 倒序：后发生的采纳在前（场景 3）
    assert [e["reason"] for e in body_b["entries"]] == ["回答被采纳", "回答被赞"]
    assert {e["source"] for e in body_b["entries"]} == {"vote", "accept"}


async def test_self_vote_not_credited_and_duplicate_vote_single_row(
    client: httpx.AsyncClient,
) -> None:
    """自投不计分 + 复投 409 不加行（幂等）。"""
    author = await _register_and_login(client)
    q = await client.post(
        "/api/v1/questions",
        json={"title": f"自投 {uuid.uuid4().hex[:6]}", "body": "正文"},
        headers=_auth(author["token"]),
    )
    question_id = q.json()["id"]
    assert (
        await client.post(
            f"/api/v1/questions/{question_id}/vote",
            json={"direction": "up"},
            headers=_auth(author["token"]),
        )
    ).status_code == 204
    # 复投（改票）→ 409
    dup = await client.post(
        f"/api/v1/questions/{question_id}/vote",
        json={"direction": "down"},
        headers=_auth(author["token"]),
    )
    assert dup.status_code == 409

    rep = await client.get(
        f"/api/v1/users/{author['id']}/reputation", headers=_auth(author["token"])
    )
    body = rep.json()
    assert body["total"] == 0  # 自投跳过：零流水
    assert body["entries"] == []


async def test_double_accept_single_ledger_entry(client: httpx.AsyncClient) -> None:
    """重复采纳 409：accept 事件仅一次，流水恰一行。"""
    author = await _register_and_login(client)
    responder = await _register_and_login(client)
    q = await client.post(
        "/api/v1/questions",
        json={"title": f"采纳 {uuid.uuid4().hex[:6]}", "body": "正文"},
        headers=_auth(author["token"]),
    )
    question_id = q.json()["id"]
    a = await client.post(
        f"/api/v1/questions/{question_id}/answers",
        json={"body": "回答正文"},
        headers=_auth(responder["token"]),
    )
    answer_id = a.json()["id"]
    assert (
        await client.post(
            f"/api/v1/answers/{answer_id}/accept", headers=_auth(author["token"])
        )
    ).status_code == 204
    assert (
        await client.post(
            f"/api/v1/answers/{answer_id}/accept", headers=_auth(author["token"])
        )
    ).status_code == 409

    rep = await client.get(
        f"/api/v1/users/{responder['id']}/reputation", headers=_auth(responder["token"])
    )
    body = rep.json()
    assert body["total"] == 15
    assert len(body["entries"]) == 1


async def test_get_reputation_visibility(client: httpx.AsyncClient) -> None:
    """仅本人（裁定 4）：他人 403；未登录 401。"""
    author = await _register_and_login(client)
    stranger = await _register_and_login(client)

    # 他人查询 → 403
    forbidden = await client.get(
        f"/api/v1/users/{author['id']}/reputation", headers=_auth(stranger["token"])
    )
    assert forbidden.status_code == 403
    # 未登录 → 401
    unauth = await client.get(f"/api/v1/users/{author['id']}/reputation")
    assert unauth.status_code == 401
    # 本人（无流水）→ 200 空
    ok = await client.get(
        f"/api/v1/users/{author['id']}/reputation", headers=_auth(author["token"])
    )
    assert ok.status_code == 200
    assert ok.json()["total"] == 0
    assert ok.json()["entries"] == []
