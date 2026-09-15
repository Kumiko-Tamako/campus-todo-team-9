"""提问接口集成测试：httpx ASGI 传输 + 真 PostgreSQL + 真 Redis（登录写 refresh）。

覆盖：201 正常发布（含 strip 端到端）/ 401 未认证 / 422 校验族 / 413 超大 body。
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
    """注册并登录，返回 (access_token, user_id)。"""
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
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["id"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _question_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "如何理解数据库第三范式？",
        "body": "教材看不太懂，求举例说明。",
    }
    payload.update(overrides)
    return payload


def _assert_no_input_echo(resp: httpx.Response) -> None:
    """422 不得回显攻击者原始输入：列表形态错误项只许有 type/loc/msg；
    字符串形态（路由捕获 ValueError）时，原始字节中也不许出现 NUL/代理转义。"""
    detail = resp.json()["detail"]
    if isinstance(detail, list):
        for item in detail:
            assert set(item.keys()) == {"type", "loc", "msg"}
    assert b"\x00" not in resp.content and b"\\u0000" not in resp.content
    assert b"\\ud800" not in resp.content


async def test_ask_question_returns_201(client: httpx.AsyncClient) -> None:
    token, user_id = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions", json=_question_payload(), headers=_auth(token)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # 白名单字段恰好 5 个，无任何内部字段
    assert set(body.keys()) == {"id", "title", "body", "author_id", "created_at"}
    assert body["author_id"] == user_id  # 作者取自令牌，非请求体
    assert body["title"] == "如何理解数据库第三范式？"
    uuid.UUID(body["id"])  # id 为合法 UUID


async def test_title_with_surrounding_spaces_is_stripped(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(title="  带空格的标题  "),
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["title"] == "带空格的标题"


async def test_ask_without_token_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/questions", json=_question_payload())
    assert resp.status_code == 401


async def test_ask_with_bad_token_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/questions", json=_question_payload(), headers=_auth("garbage.token")
    )
    assert resp.status_code == 401


async def test_empty_title_returns_422(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions", json=_question_payload(title=""), headers=_auth(token)
    )
    assert resp.status_code == 422


async def test_blank_title_returns_422(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions", json=_question_payload(title="    "), headers=_auth(token)
    )
    assert resp.status_code == 422


async def test_title_too_long_returns_422(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(title="a" * 101),
        headers=_auth(token),
    )
    assert resp.status_code == 422


async def test_body_too_long_returns_422(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(body="x" * 5001),
        headers=_auth(token),
    )
    assert resp.status_code == 422


async def test_missing_body_returns_422(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions", json={"title": "只有标题"}, headers=_auth(token)
    )
    assert resp.status_code == 422


async def test_extra_field_returns_422(client: httpx.AsyncClient) -> None:
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(hacker=1),
        headers=_auth(token),
    )
    assert resp.status_code == 422


async def test_oversized_body_returns_413(client: httpx.AsyncClient) -> None:
    # body_limit 中间件在路由/鉴权之外层：超限直接 413，不进 schema 校验
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(body="a" * (1024 * 1024 + 100)),
        headers=_auth(token),
    )
    assert resp.status_code == 413


async def test_nul_in_title_returns_422(client: httpx.AsyncClient) -> None:
    # P-01：NUL 无法存入 PostgreSQL，值对象在落库前拦截（旧行为 500）
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(title="a\x00b 攻击"),
        headers=_auth(token),
    )
    assert resp.status_code == 422
    _assert_no_input_echo(resp)


async def test_nul_in_body_returns_422(client: httpx.AsyncClient) -> None:
    # P-02：正文 NUL 同样 422
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        json=_question_payload(body="x\x00y"),
        headers=_auth(token),
    )
    assert resp.status_code == 422
    _assert_no_input_echo(resp)


async def test_lone_surrogate_title_returns_422(client: httpx.AsyncClient) -> None:
    # P-03：lone surrogate 被 Pydantic 拦截；422 处理器不回显 input，
    # 避免响应体 UTF-8 编码崩溃（旧行为 UnicodeEncodeError → 500）
    token, _ = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/questions",
        content=b'{"title":"\\ud800\\ud800","body":"ok"}',
        headers={**_auth(token), "content-type": "application/json"},
    )
    assert resp.status_code == 422
    _assert_no_input_echo(resp)


async def test_recursive_bomb_returns_422(client: httpx.AsyncClient) -> None:
    # P-04：depth=2000 的 JSON（12KB，绕过 1MB body 上限）；422 处理器不递归
    # 遍历回显 input，避免 jsonable_encoder 爆栈（旧行为 RecursionError → 500）
    token, _ = await _register_and_login(client)
    bomb = b'{"a":' * 2000 + b"1" + b"}" * 2000
    resp = await client.post(
        "/api/v1/questions",
        content=bomb,
        headers={**_auth(token), "content-type": "application/json"},
    )
    assert resp.status_code == 422
    _assert_no_input_echo(resp)


# ============================================================
# 2.5 列表 + 2.6 详情（访客可用，全部无鉴权头）
# ============================================================


async def test_list_guest_access_whitelist(client: httpx.AsyncClient) -> None:
    """S-01/S-12：访客可用；响应与条目均为白名单字段（无正文/密码哈希/内部字段）。"""
    resp = await client.get("/api/v1/questions")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"items", "total", "page", "page_size", "total_pages"}
    assert data["page"] == 1 and data["page_size"] == 20
    for item in data["items"]:
        assert set(item.keys()) == {"id", "title", "author_id", "created_at"}
    if data["items"]:
        assert data["total_pages"] == -(-data["total"] // data["page_size"])


async def test_list_page_non_positive_returns_422(client: httpx.AsyncClient) -> None:
    """S-02/S-04 族：page 非法 → 422，不 500，不回显输入。"""
    for bad in ("0", "-1"):
        resp = await client.get("/api/v1/questions", params={"page": bad})
        assert resp.status_code == 422
        _assert_no_input_echo(resp)


async def test_list_page_beyond_total_returns_200_empty(client: httpx.AsyncClient) -> None:
    """S-03（约定）：超总页 → 200 空列表，page 原样回显。"""
    resp = await client.get("/api/v1/questions", params={"page": 999999})
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["page"] == 999999


async def test_list_page_size_non_positive_returns_422(client: httpx.AsyncClient) -> None:
    """S-04：page_size ≤ 0 → 422。"""
    for bad in ("0", "-5"):
        resp = await client.get("/api/v1/questions", params={"page_size": bad})
        assert resp.status_code == 422
        _assert_no_input_echo(resp)


async def test_list_page_size_over_limit_422_and_boundary_100_ok(
    client: httpx.AsyncClient,
) -> None:
    """S-05：page_size 上限 100 → 超限 422；边界 100 恰好 200。"""
    for bad in (100000, 101):
        resp = await client.get("/api/v1/questions", params={"page_size": bad})
        assert resp.status_code == 422
        _assert_no_input_echo(resp)
    resp = await client.get("/api/v1/questions", params={"page_size": 100})
    assert resp.status_code == 200
    assert resp.json()["page_size"] == 100


async def test_list_ignores_unknown_sort_param(client: httpx.AsyncClient) -> None:
    """S-07（A 方案约定）：迭代 1 无排序功能，未知 query 参数被忽略——
    sort 不进 SQL、无注入面，仍 200 且保持"最新优先"默认序，不 500。"""
    token, _ = await _register_and_login(client)
    r = await client.post("/api/v1/questions", json=_question_payload(), headers=_auth(token))
    assert r.status_code == 201
    posted_id = r.json()["id"]
    resp = await client.get("/api/v1/questions", params={"sort": "(SELECT 1)"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1 and data["page_size"] == 20
    assert data["items"][0]["id"] == posted_id


async def test_list_pagination_exact_slicing_s08(client: httpx.AsyncClient) -> None:
    """S-08：连发 25 帖（本测试为全表最新块）→ 第 1 页恰为其最新 20 帖，
    第 2 页补足其余 5 帖，跨页不重复。"""
    token, _ = await _register_and_login(client)
    ids: list[str] = []
    for i in range(25):
        r = await client.post(
            "/api/v1/questions",
            json=_question_payload(title=f"S08 分页标题 {i:02d}"),
            headers=_auth(token),
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])

    d1 = (await client.get("/api/v1/questions", params={"page": 1, "page_size": 20})).json()
    assert d1["total"] >= 25 and d1["total_pages"] >= 2
    assert len(d1["items"]) == 20
    ids1 = {item["id"] for item in d1["items"]}
    assert ids1 == set(ids[5:])  # 最新 20 帖（ids[0] 最旧）

    d2 = (await client.get("/api/v1/questions", params={"page": 2, "page_size": 20})).json()
    ids2 = {item["id"] for item in d2["items"]}
    assert set(ids[:5]) <= ids2  # 剩余 5 帖在第 2 页
    assert not ids1 & ids2  # 跨页无重复


async def test_posted_question_immediately_first_in_list(
    client: httpx.AsyncClient,
) -> None:
    """S-14/US-Q04：发布后立即可见且居首（page_size=1 的第 1 项即新帖）。"""
    token, _ = await _register_and_login(client)
    r = await client.post(
        "/api/v1/questions",
        json=_question_payload(title="立即可见标题"),
        headers=_auth(token),
    )
    posted_id = r.json()["id"]
    resp = await client.get("/api/v1/questions", params={"page": 1, "page_size": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["page_size"] == 1 and len(data["items"]) == 1
    assert data["items"][0]["id"] == posted_id


async def test_detail_returns_full_whitelist_fields(client: httpx.AsyncClient) -> None:
    """S-09：详情字段完整；tags/answers 迭代 1 恒为空列表。"""
    token, user_id = await _register_and_login(client)
    r = await client.post(
        "/api/v1/questions",
        json=_question_payload(title="详情标题", body="详情正文明细"),
        headers=_auth(token),
    )
    assert r.status_code == 201
    qid = r.json()["id"]
    resp = await client.get(f"/api/v1/questions/{qid}")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {
        "id", "title", "body", "author_id", "created_at", "tags", "answers",
    }
    assert data["title"] == "详情标题"
    assert data["body"] == "详情正文明细"
    assert data["author_id"] == user_id
    assert data["tags"] == [] and data["answers"] == []


async def test_detail_missing_returns_404_without_internal_info(
    client: httpx.AsyncClient,
) -> None:
    """S-10：合法 UUID 但不存在 → 404，只回业务语义，无内部错误栈。"""
    resp = await client.get(f"/api/v1/questions/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "问题不存在"}
    assert "Traceback" not in resp.text


async def test_detail_invalid_id_returns_422(client: httpx.AsyncClient) -> None:
    """S-11：格式非法 ID → 422（路径校验拦截），不 500。"""
    for bad in ("abc", "not-a-uuid"):
        resp = await client.get(f"/api/v1/questions/{bad}")
        assert resp.status_code == 422
        _assert_no_input_echo(resp)
