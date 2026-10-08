"""LoginUseCase 单元测试：fake 仓储/哈希器/令牌服务/刷新存储/失败守卫，不连库。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.contexts.identity.application.commands import LoginCommand
from app.contexts.identity.application.login_use_case import LoginUseCase
from app.contexts.identity.application.ports import REFRESH_TOKEN_TTL
from app.contexts.identity.domain.errors import AccountLockedError, InvalidCredentialsError
from app.contexts.identity.domain.user import User
from app.contexts.identity.domain.value_objects import Email, PasswordHash, StaffId, StudentId


def _make_user(*, student_id: str | None = "2025010101", staff_id: str | None = None) -> User:
    return User(
        id=uuid4(),
        role="teacher" if staff_id is not None else "student",
        email=Email("zhang@stu.edu.cn"),
        password_hash=PasswordHash("$2b$12$fakehash"),
        student_id=StudentId(student_id) if student_id is not None else None,
        staff_id=StaffId(staff_id) if staff_id is not None else None,
        created_at=datetime.now(UTC),
    )


class FakeRepository:
    def __init__(self, users: list[User]) -> None:
        self.users = users

    async def get_by_student_id(self, student_id: str) -> User | None:
        return next(
            (
                u
                for u in self.users
                if u.student_id is not None and u.student_id.value == student_id
            ),
            None,
        )

    async def get_by_staff_id(self, staff_id: str) -> User | None:
        return next(
            (u for u in self.users if u.staff_id is not None and u.staff_id.value == staff_id),
            None,
        )

    async def get_by_id(self, user_id: UUID) -> User | None:
        return next((u for u in self.users if u.id == user_id), None)


class FakeHasher:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid

    async def hash(self, plain: str) -> str:
        return "$2b$12$fakehash"

    async def verify(self, plain: str, hashed: str) -> bool:
        return self.valid


class FakeTokenService:
    def issue_access(self, user: User) -> str:
        return "access-token"

    def issue_refresh(self, user: User) -> tuple[str, UUID]:
        return "refresh-token", uuid4()

    def verify_access(self, token: str) -> UUID | None:
        return None

    def decode_refresh(self, token: str) -> tuple[UUID, UUID] | None:
        return None


class FakeRefreshStore:
    def __init__(self) -> None:
        self.saved: list[tuple[UUID, UUID, object]] = []

    async def save(self, jti: UUID, user_id: UUID, ttl: object) -> None:
        self.saved.append((jti, user_id, ttl))

    async def consume(self, jti: UUID) -> UUID | None:
        return None

    async def revoke(self, jti: UUID) -> None:
        pass


class FakeLoginAttemptGuard:
    """内存版失败守卫：记录调用序列，可预置锁定态（单测不连 Redis）。"""

    def __init__(self, *, locked: bool = False) -> None:
        self.locked = locked
        self.failures: list[str] = []
        self.cleared: list[str] = []

    async def check_locked(self, identifier: str) -> bool:
        return self.locked

    async def record_failure(self, identifier: str) -> None:
        self.failures.append(identifier)

    async def clear(self, identifier: str) -> None:
        self.cleared.append(identifier)


def _use_case(
    *,
    users: list[User] | None = None,
    valid_password: bool = True,
    guard: FakeLoginAttemptGuard | None = None,
) -> tuple[LoginUseCase, FakeRefreshStore, FakeLoginAttemptGuard]:
    repo = FakeRepository(users if users is not None else [_make_user()])
    store = FakeRefreshStore()
    attempt_guard = guard if guard is not None else FakeLoginAttemptGuard()
    use_case = LoginUseCase(
        repo, FakeHasher(valid_password), FakeTokenService(), store, attempt_guard
    )
    return use_case, store, attempt_guard


async def test_login_student_success() -> None:
    use_case, store, guard = _use_case()
    result = await use_case.execute(LoginCommand(identifier="2025010101", password="Passw0rd8"))
    assert result.access_token == "access-token"
    assert result.refresh_token == "refresh-token"
    assert result.user.role == "student"
    # Refresh 令牌已入存储（jti, user_id, TTL）
    assert len(store.saved) == 1
    assert store.saved[0][2] == REFRESH_TOKEN_TTL
    assert guard.cleared == ["2025010101"]  # 成功即清零失败计数


async def test_login_teacher_by_staff_id() -> None:
    teacher = _make_user(student_id=None, staff_id="T10086")
    use_case, _, _ = _use_case(users=[teacher])
    result = await use_case.execute(LoginCommand(identifier="T10086", password="Passw0rd8"))
    assert result.user.role == "teacher"


async def test_wrong_password_rejected() -> None:
    use_case, store, guard = _use_case(valid_password=False)
    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(LoginCommand(identifier="2025010101", password="WrongPass1"))
    assert store.saved == []  # 登录失败不签发令牌、不落存储
    assert guard.failures == ["2025010101"]  # 密码错计一次失败


async def test_unknown_identifier_rejected() -> None:
    use_case, _, guard = _use_case(users=[])
    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(LoginCommand(identifier="2025999999", password="Passw0rd8"))
    assert guard.failures == ["2025999999"]  # 不存在的 identifier 同样计数（防枚举）


async def test_error_message_indistinguishable() -> None:
    """防枚举：用户不存在与密码错误的异常消息完全一致。"""
    unknown_repo = FakeRepository([])
    unknown_case = LoginUseCase(
        unknown_repo,
        FakeHasher(True),
        FakeTokenService(),
        FakeRefreshStore(),
        FakeLoginAttemptGuard(),
    )
    wrong_repo = FakeRepository([_make_user()])
    wrong_case = LoginUseCase(
        wrong_repo,
        FakeHasher(False),
        FakeTokenService(),
        FakeRefreshStore(),
        FakeLoginAttemptGuard(),
    )

    with pytest.raises(InvalidCredentialsError) as exc_unknown:
        await unknown_case.execute(LoginCommand(identifier="2025999999", password="Passw0rd8"))
    with pytest.raises(InvalidCredentialsError) as exc_wrong:
        await wrong_case.execute(LoginCommand(identifier="2025010101", password="WrongPass1"))

    assert str(exc_unknown.value) == str(exc_wrong.value)


async def test_locked_identifier_rejected_before_credentials() -> None:
    """锁定态：即使密码正确也 423 语义（AccountLockedError），不验密、不签发、不计数。"""
    guard = FakeLoginAttemptGuard(locked=True)
    use_case, store, _ = _use_case(guard=guard)
    with pytest.raises(AccountLockedError):
        await use_case.execute(LoginCommand(identifier="2025010101", password="Passw0rd8"))
    assert store.saved == []
    assert guard.failures == [] and guard.cleared == []