"""JWT 令牌安全测试：纯 token_service，不连库不连 Redis，进 CI。

覆盖《暴力测试方案》第三节的 L-07（令牌类型混用）、L-08（篡改签名）、
L-09（alg:none）、L-10（过期）——这些是纯 JWT 层防线。
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jose import jwt

from app.contexts.identity.domain.user import User
from app.contexts.identity.domain.value_objects import Email, PasswordHash
from app.contexts.identity.infrastructure.token_service import JwtTokenService

SECRET = "test-secret"
service = JwtTokenService(SECRET)


def _user() -> User:
    return User(
        id=uuid4(),
        role="student",
        email=Email("a@stu.edu.cn"),
        password_hash=PasswordHash("$2b$12$h"),
        student_id=None,
        staff_id=None,
        created_at=datetime.now(UTC),
    )


def _encode(**claims: object) -> str:
    return jwt.encode(claims, SECRET, algorithm="HS256")


def _unsigned_token(**claims: object) -> str:
    """手工构造无签名 JWT（header alg:none）：模拟攻击者令牌。"""
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    body_b64 = base64.urlsafe_b64encode(json.dumps(claims, default=str).encode())
    return f"{header_b64.rstrip(b'=').decode()}.{body_b64.rstrip(b'=').decode()}."


def test_access_token_roundtrip() -> None:
    user = _user()
    token = service.issue_access(user)
    assert service.verify_access(token) == user.id


def test_refresh_token_roundtrip_with_jti() -> None:
    user = _user()
    token, jti = service.issue_refresh(user)
    decoded = service.decode_refresh(token)
    assert decoded is not None
    assert decoded[0] == user.id
    assert decoded[1] == jti


def test_access_token_used_as_refresh_rejected() -> None:
    """L-07：Access 令牌当 Refresh 用必须被拒（typ 不匹配）。"""
    user = _user()
    access = service.issue_access(user)
    assert service.decode_refresh(access) is None


def test_refresh_token_used_as_access_rejected() -> None:
    """L-07 反向：Refresh 令牌当 Access 用必须被拒。"""
    user = _user()
    refresh, _ = service.issue_refresh(user)
    assert service.verify_access(refresh) is None


def test_alg_none_token_rejected() -> None:
    """L-09：alg:none 无签名令牌必须被拒（decode 钉死 HS256）。"""
    now = datetime.now(UTC)
    none_token = _unsigned_token(
        sub=str(uuid4()),
        typ="access",
        iat=now,
        exp=now + timedelta(minutes=15),
    )
    assert service.verify_access(none_token) is None


def test_tampered_signature_rejected() -> None:
    """L-08：篡改签名中段字符后签名校验失败。

    不碰末字符：HS256 签名 32 字节 → 43 字符 base64url，末字符低 2 bit 是
    base64 填充位（解码时被丢弃），原字符为 'U' 时替换为 'X' 会解码出完全
    相同的字节（'U'=20、'X'=23 高 4 位同为 0101），签名校验照样通过，
    造成约 1/16 概率的假绿/假红 flaky。签名前 40 字符的 6 bit 全部承载数据，
    篡改中段任意一个字符必然改变解码字节 → 确定性拒绝。
    """
    user = _user()
    token = service.issue_access(user)
    header_payload, sep, signature = token.rpartition(".")
    middle = len(signature) // 2
    replacement = "A" if signature[middle] != "A" else "B"
    tampered_sig = f"{signature[:middle]}{replacement}{signature[middle + 1 :]}"
    tampered = f"{header_payload}{sep}{tampered_sig}"
    # 确定性证据（非概率性回归仪式）：中段 6 bit 全部承载数据，
    # 篡改后解码字节必与原签名不同——此断言失败即说明篡改落在了填充位
    pad = "=" * (-len(signature) % 4)
    assert base64.urlsafe_b64decode(
        signature + pad
    ) != base64.urlsafe_b64decode(tampered_sig + pad)
    assert service.verify_access(tampered) is None


def test_expired_access_token_rejected() -> None:
    """L-10：过期令牌必须被拒。"""
    past = datetime.now(UTC) - timedelta(minutes=16)
    expired = _encode(sub=str(uuid4()), typ="access", iat=past, exp=past + timedelta(minutes=15))
    assert service.verify_access(expired) is None


def test_forged_access_with_malformed_sub_returns_none() -> None:
    """补测 F-03：签名合法但 sub 非 UUID 的伪造 Access → 返回 None（不抛 500）。"""
    now = datetime.now(UTC)
    forged = _encode(sub="attacker", typ="access", iat=now, exp=now + timedelta(minutes=15))
    assert service.verify_access(forged) is None


def test_forged_refresh_with_malformed_claims_returns_none() -> None:
    """补测 F-01/F-02/F-06：签名合法但 sub/jti 非 UUID 的伪造 Refresh → 返回 None（不抛 500）。"""
    now = datetime.now(UTC)
    forged = _encode(
        sub="attacker",
        typ="refresh",
        jti="not-a-uuid",
        iat=now,
        exp=now + timedelta(days=7),
    )
    assert service.decode_refresh(forged) is None
