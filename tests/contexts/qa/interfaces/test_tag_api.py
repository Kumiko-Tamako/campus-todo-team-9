"""标签接口集成测试：httpx ASGI + 真 PostgreSQL。

覆盖（1.3 功能域 5/10 + v6 双 422 形态）：
- GET /api/v1/tags 访客可用、码点序、同名唯一
- 提问带合法标签 → 201 含规范名列表；详情/列表回显 tags
- 6 个不同标签 → 422 字符串形（含"至多 5 个标签"）
- 白名单外字符 → 422 字符串形（含"不支持的字符"）
- tags 传字符串（类型错）→ 422 数组形（pydantic，不回显输入）
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


async def _register_and_login(client: httpx.AsyncClient) -> str:
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
    return login.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _question_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"title": f"标签测试 {uuid.uuid4().hex[:6]}", "body": "正文"}
    payload.update(overrides)
    return payload


async def test_ask_with_tags_returns_canonical_list(client: httpx.AsyncClient) -> None:
    token = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(tags=["数据库", "SQL", "sql"]),
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tags"] == ["SQL", "数据库"]  # 去重 + 码点序（ASCII < CJK）

    detail = await client.get(f"/api/v1/questions/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["tags"] == ["SQL", "数据库"]

    listing = await client.get("/api/v1/questions?page=1&page_size=100")
    item = next(q for q in listing.json()["items"] if q["id"] == body["id"])
    assert item["tags"] == ["SQL", "数据库"]


async def test_six_unique_tags_returns_422_string_shape(client: httpx.AsyncClient) -> None:
    token = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(tags=["a1", "b2", "c3", "d4", "e5", "f6"]),
        headers=_auth(token),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str)  # 领域校验 → 字符串形
    assert "至多 5 个标签" in detail


async def test_dedupe_before_count_allows_six_raw(client: httpx.AsyncClient) -> None:
    """6 个原始串去重后 5 个 → 合法（上限按去重后计，1.3 功能域 10）。"""
    token = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(tags=["A", "a", "b", "c", "d", "e"]),
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    assert len(resp.json()["tags"]) == 5


async def test_illegal_tag_char_returns_422_string_shape(client: httpx.AsyncClient) -> None:
    token = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(tags=["标签🔥"]),
        headers=_auth(token),
    )
    assert resp.status_code == 422
    assert "不支持的字符" in resp.json()["detail"]


async def test_tags_wrong_type_returns_422_array_shape(client: httpx.AsyncClient) -> None:
    """tags 传字符串（非数组）→ pydantic 数组形 422，且不回显输入。"""
    token = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(tags="数据库"),
        headers=_auth(token),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    for item in detail:
        assert set(item.keys()) == {"type", "loc", "msg"}


async def test_list_tags_visitor_ok_unique_sorted(client: httpx.AsyncClient) -> None:
    """GET /tags 访客可用；同名唯一（T02）：两帖用 "SQL"/"sql" → 目录只现一次。"""
    token = await _register_and_login(client)
    suffix = uuid.uuid4().hex[:6]
    r1 = await client.post(
        "/api/v1/questions", json=_question_payload(tags=[f"zz{suffix}"]), headers=_auth(token)
    )
    r2 = await client.post(
        "/api/v1/questions",
        json=_question_payload(tags=[f"ZZ{suffix}"]),
        headers=_auth(token),
    )
    assert r1.status_code == 201 and r2.status_code == 201

    resp = await client.get("/api/v1/tags")  # 无 Authorization → 访客
    assert resp.status_code == 200
    tags = resp.json()["tags"]
    assert tags.count(f"zz{suffix}") == 1  # 同名唯一
    assert tags == sorted(tags)  # 码点序
