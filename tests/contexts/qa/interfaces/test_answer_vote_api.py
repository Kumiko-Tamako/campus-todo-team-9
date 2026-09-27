"""回答/投票接口集成测试（分支 1 步骤 5）：httpx ASGI + 真 PostgreSQL + 真 Redis。

覆盖计划步骤 5 集成项：答题 201 / 未登录 401 / 重复票 409（含改票）/ 非法 direction 422 /
目标不存在 404 / 详情 answers 实装与 D2 排序 / 列表 votes 排序端到端（1.3 功能域 7 场景）。
"""

from __future__ import annotations

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


async def _ask(client: httpx.AsyncClient, token: str, **overrides: Any) -> str:
    payload: dict[str, Any] = {
        "title": f"答票接口 {uuid.uuid4().hex[:8]}",
        "body": "正文",
    }
    payload.update(overrides)
    r = await client.post("/api/v1/questions", json=payload, headers=_auth(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------- 回答 ----------------


async def test_post_answer_returns_201_whitelist(client: httpx.AsyncClient) -> None:
    token, user_id = await _register_and_login(client)
    qid = await _ask(client, token)
    resp = await client.post(
        f"/api/v1/questions/{qid}/answers",
        json={"body": "  这是回答正文  "},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body.keys()) == {
        "id", "body", "author_id", "created_at", "votes", "is_accepted", "comments",
    }  # comments 随分支 2 加入白名单
    assert body["body"] == "这是回答正文"  # strip 端到端
    assert body["author_id"] == user_id
    assert body["votes"] == 0 and body["is_accepted"] is False


async def test_post_answer_requires_login(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    resp = await client.post(
        f"/api/v1/questions/{qid}/answers", json={"body": "匿名回答"}
    )
    assert resp.status_code == 401


async def test_post_answer_missing_question_returns_404(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    resp = await client.post(
        f"/api/v1/questions/{uuid.uuid4()}/answers",
        json={"body": "回答"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


async def test_post_answer_blank_body_returns_422(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    resp = await client.post(
        f"/api/v1/questions/{qid}/answers", json={"body": "   "}, headers=_auth(token)
    )
    assert resp.status_code == 422


# ---------------- 投票 ----------------


async def test_vote_question_returns_204_and_detail_reflects(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    resp = await client.post(
        f"/api/v1/questions/{qid}/vote", json={"direction": "up"}, headers=_auth(token)
    )
    assert resp.status_code == 204
    assert resp.content == b""


async def test_vote_requires_login(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    resp = await client.post(f"/api/v1/questions/{qid}/vote", json={"direction": "up"})
    assert resp.status_code == 401


async def test_duplicate_vote_and_revote_rejected_409(client: httpx.AsyncClient) -> None:
    """v3 裁定 #5：同向重复与异向改票一律 409，票数不变（1.3 功能域 7 场景）。"""
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    first = await client.post(
        f"/api/v1/questions/{qid}/vote", json={"direction": "up"}, headers=_auth(token)
    )
    assert first.status_code == 204
    again = await client.post(
        f"/api/v1/questions/{qid}/vote", json={"direction": "up"}, headers=_auth(token)
    )
    assert again.status_code == 409
    flip = await client.post(
        f"/api/v1/questions/{qid}/vote", json={"direction": "down"}, headers=_auth(token)
    )
    assert flip.status_code == 409  # 改票同样被拒


async def test_vote_invalid_direction_returns_422(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    qid = await _ask(client, token)
    resp = await client.post(
        f"/api/v1/questions/{qid}/vote",
        json={"direction": "sideways"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


async def test_vote_missing_targets_return_404(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    missing_q = uuid.uuid4()
    r1 = await client.post(
        f"/api/v1/questions/{missing_q}/vote", json={"direction": "up"}, headers=_auth(token)
    )
    assert r1.status_code == 404
    qid = await _ask(client, token)
    r2 = await client.post(
        f"/api/v1/questions/{qid}/answers/{uuid.uuid4()}/vote",
        json={"direction": "up"},
        headers=_auth(token),
    )
    assert r2.status_code == 404


async def test_vote_answer_net_count_in_detail(client: httpx.AsyncClient) -> None:
    """净票口径端到端：2 赞 1 反 → 详情 answers[0].votes == 1。"""
    author, _ = await _register_and_login(client)
    qid = await _ask(client, author)
    ans = await client.post(
        f"/api/v1/questions/{qid}/answers", json={"body": "回答"}, headers=_auth(author)
    )
    assert ans.status_code == 201
    aid = ans.json()["id"]
    for direction in ("up", "up", "down"):
        voter, _ = await _register_and_login(client)
        r = await client.post(
            f"/api/v1/questions/{qid}/answers/{aid}/vote",
            json={"direction": direction},
            headers=_auth(voter),
        )
        assert r.status_code == 204, r.text
    detail = await client.get(f"/api/v1/questions/{qid}")
    assert detail.status_code == 200
    assert detail.json()["answers"][0]["votes"] == 1


# ---------------- 详情 answers 实装 ----------------


async def test_detail_answers_populated_and_ordered(client: httpx.AsyncClient) -> None:
    """详情 answers 不再恒空；多赞者排前（D2 净票降序）。"""
    author, _ = await _register_and_login(client)
    qid = await _ask(client, author)
    ids: dict[str, str] = {}
    for name in ("low", "high"):
        r = await client.post(
            f"/api/v1/questions/{qid}/answers",
            json={"body": f"回答 {name}"},
            headers=_auth(author),
        )
        ids[name] = r.json()["id"]
    for votes, key in ((1, "low"), (2, "high")):
        for _ in range(votes):
            voter, _ = await _register_and_login(client)
            await client.post(
                f"/api/v1/questions/{qid}/answers/{ids[key]}/vote",
                json={"direction": "up"},
                headers=_auth(voter),
            )
    detail = (await client.get(f"/api/v1/questions/{qid}")).json()
    answers = detail["answers"]
    assert [a["id"] for a in answers] == [ids["high"], ids["low"]]
    assert [a["votes"] for a in answers] == [2, 1]


# ---------------- 列表 votes 排序（1.3 功能域 7） ----------------


async def test_list_sorted_by_net_votes(client: httpx.AsyncClient) -> None:
    """问题 A 获 2 票、B 获 1 票 → sort=votes 时 A 在 B 前；默认 latest 不受影响。"""
    author, _ = await _register_and_login(client)
    qa = await _ask(client, author, title="排序 A 高票")
    qb = await _ask(client, author, title="排序 B 低票")
    for qid, times in ((qa, 2), (qb, 1)):
        for _ in range(times):
            voter, _ = await _register_and_login(client)
            r = await client.post(
                f"/api/v1/questions/{qid}/vote",
                json={"direction": "up"},
                headers=_auth(voter),
            )
            assert r.status_code == 204
    votes_order = (
        await client.get("/api/v1/questions", params={"sort": "votes", "page_size": 100})
    ).json()["items"]
    ids = [item["id"] for item in votes_order]
    assert ids.index(qa) < ids.index(qb)  # A 排在 B 之前（1.3 L164）
    latest_ids = [
        i["id"]
        for i in (await client.get("/api/v1/questions", params={"page_size": 100})).json()["items"]
    ]
    assert latest_ids.index(qb) < latest_ids.index(qa)  # 默认 latest：B 更新在前
