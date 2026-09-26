"""采纳/评论接口集成测试（分支 2 步骤 5）：httpx ASGI + 真 PostgreSQL + 真 Redis。

覆盖：题评/答评 201 / 未登录 401 / 目标不存在 404 / 空白正文 422 /
采纳 204 / 非提问者 403 / 重复采纳 409 / 回答不存在 404 /
详情实装 accepted_answer_id + comments 分组（v3 裁定 #3、1.3 功能域 8/9）。
"""

from __future__ import annotations

import uuid

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


async def _register_and_login(client: httpx.AsyncClient) -> tuple[str, str]:
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
    token = login.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    assert me.status_code == 200, me.text
    return token, me.json()["id"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _ask(client: httpx.AsyncClient, token: str) -> str:
    r = await client.post(
        "/api/v1/questions",
        json={"title": f"采纳评论 {uuid.uuid4().hex[:8]}", "body": "正文"},
        headers=_auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _answer(client: httpx.AsyncClient, token: str, qid: str) -> str:
    r = await client.post(
        f"/api/v1/questions/{qid}/answers", json={"body": "回答"}, headers=_auth(token)
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------- 评论 ----------------


async def test_comment_question_returns_201_whitelist(client: httpx.AsyncClient) -> None:
    token, user_id = await _register_and_login(client)
    qid = await _ask(client, token)
    resp = await client.post(
        f"/api/v1/questions/{qid}/comments",
        json={"body": "  可以参考教材第 3 章  "},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body.keys()) == {"id", "body", "author_id", "created_at"}
    assert body["body"] == "可以参考教材第 3 章"  # strip 端到端
    assert body["author_id"] == user_id
    # 出现在问题详情的评论列表（1.3 功能域 9 场景）
    detail = (await client.get(f"/api/v1/questions/{qid}")).json()
    assert [c["id"] for c in detail["comments"]] == [body["id"]]


async def test_comment_answer_nested_in_detail(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    aid = await _answer(client, token, qid)
    resp = await client.post(
        f"/api/v1/answers/{aid}/comments",
        json={"body": "答评内容"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    detail = (await client.get(f"/api/v1/questions/{qid}")).json()
    assert detail["comments"] == []  # 答评不混入题评
    assert [c["body"] for c in detail["answers"][0]["comments"]] == ["答评内容"]


async def test_comment_requires_login(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    r1 = await client.post(f"/api/v1/questions/{qid}/comments", json={"body": "匿名"})
    assert r1.status_code == 401
    aid = await _answer(client, token, qid)
    r2 = await client.post(f"/api/v1/answers/{aid}/comments", json={"body": "匿名"})
    assert r2.status_code == 401


async def test_comment_missing_targets_return_404(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    r1 = await client.post(
        f"/api/v1/questions/{uuid.uuid4()}/comments", json={"body": "x"}, headers=_auth(token)
    )
    assert r1.status_code == 404
    r2 = await client.post(
        f"/api/v1/answers/{uuid.uuid4()}/comments", json={"body": "x"}, headers=_auth(token)
    )
    assert r2.status_code == 404


async def test_comment_blank_or_oversized_body_returns_422(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    for bad in ("   ", "A" * 5001):
        r = await client.post(
            f"/api/v1/questions/{qid}/comments", json={"body": bad}, headers=_auth(token)
        )
        assert r.status_code == 422
    r = await client.post(
        f"/api/v1/questions/{qid}/comments",
        json={"body": "x", "author_id": "fake"},
        headers=_auth(token),
    )
    assert r.status_code == 422  # extra=forbid 冒名封死


# ---------------- 采纳 ----------------


async def test_accept_returns_204_and_detail_reflects(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    aid = await _answer(client, token, qid)
    resp = await client.post(f"/api/v1/answers/{aid}/accept", headers=_auth(token))
    assert resp.status_code == 204
    assert resp.content == b""
    detail = (await client.get(f"/api/v1/questions/{qid}")).json()
    assert detail["accepted_answer_id"] == aid  # v3 裁定 #3 顶层返回
    assert detail["answers"][0]["is_accepted"] is True


async def test_accept_by_non_author_returns_403(client: httpx.AsyncClient) -> None:
    author_token, _ = await _register_and_login(client)
    other_token, _ = await _register_and_login(client)
    qid = await _ask(client, author_token)
    aid = await _answer(client, author_token, qid)
    resp = await client.post(f"/api/v1/answers/{aid}/accept", headers=_auth(other_token))
    assert resp.status_code == 403
    # 403 后状态不变
    detail = (await client.get(f"/api/v1/questions/{qid}")).json()
    assert detail["accepted_answer_id"] is None


async def test_reaccept_returns_409(client: httpx.AsyncClient) -> None:
    """一题一采纳：第二次采纳（换答案/同答案）一律 409。"""
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    a1 = await _answer(client, token, qid)
    a2 = await _answer(client, token, qid)
    r = await client.post(f"/api/v1/answers/{a1}/accept", headers=_auth(token))
    assert r.status_code == 204
    r = await client.post(f"/api/v1/answers/{a2}/accept", headers=_auth(token))
    assert r.status_code == 409  # 换答案再采纳被拒
    r = await client.post(f"/api/v1/answers/{a1}/accept", headers=_auth(token))
    assert r.status_code == 409  # 同答案重复采纳被拒
    detail = (await client.get(f"/api/v1/questions/{qid}")).json()
    assert detail["accepted_answer_id"] == a1  # 首采纳生效不变


async def test_accept_missing_answer_returns_404(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    resp = await client.post(f"/api/v1/answers/{uuid.uuid4()}/accept", headers=_auth(token))
    assert resp.status_code == 404


async def test_accept_requires_login(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    aid = await _answer(client, token, qid)
    resp = await client.post(f"/api/v1/answers/{aid}/accept")
    assert resp.status_code == 401


# ---------------- 采纳 × 排序联动（1.3 功能域 8） ----------------


async def test_accepted_low_vote_answer_sorts_above_high_vote(
    client: httpx.AsyncClient,
) -> None:
    """被采纳回答（0 票）优先于高票未采纳回答（1.3 L184-189）。"""
    author_token, _ = await _register_and_login(client)
    qid = await _ask(client, author_token)
    a_low = await _answer(client, author_token, qid)
    a_hi = await _answer(client, author_token, qid)
    for _ in range(3):
        voter, _ = await _register_and_login(client)
        r = await client.post(
            f"/api/v1/questions/{qid}/answers/{a_hi}/vote",
            json={"direction": "up"},
            headers=_auth(voter),
        )
        assert r.status_code == 204
    accept = await client.post(f"/api/v1/answers/{a_low}/accept", headers=_auth(author_token))
    assert accept.status_code == 204
    detail = (await client.get(f"/api/v1/questions/{qid}")).json()
    answers = detail["answers"]
    assert [a["id"] for a in answers] == [a_low, a_hi]
    assert answers[0]["is_accepted"] is True and answers[0]["votes"] == 0
    assert answers[1]["votes"] == 3
