"""User 聚合与值对象的单元测试（不连库、不依赖框架）。"""

import pytest

from app.contexts.identity.domain.errors import IdentityRequiredError, WeakPasswordError
from app.contexts.identity.domain.user import User, validate_password_strength
from app.contexts.identity.domain.value_objects import Email, PasswordHash, StaffId, StudentId


class TestPasswordStrength:
    def test_valid_password_passes(self) -> None:
        validate_password_strength("Passw0rd8")  # 不抛即通过

    @pytest.mark.parametrize(
        "bad",
        ["abc123", "abcdefgh", "12345678", "Ab1", "A1b2", "........."],
    )
    def test_invalid_password_rejected(self, bad: str) -> None:
        with pytest.raises(WeakPasswordError):
            validate_password_strength(bad)


class TestValueObjects:
    def test_student_id_valid(self) -> None:
        assert StudentId("2025010101").value == "2025010101"

    @pytest.mark.parametrize("bad", ["abc", "2025010", "2025010101010101", "2025-0101"])
    def test_student_id_invalid_format(self, bad: str) -> None:
        with pytest.raises(ValueError, match="学号"):
            StudentId(bad)

    def test_staff_id_valid(self) -> None:
        assert StaffId("T10086").value == "T10086"

    def test_staff_id_invalid_format(self) -> None:
        with pytest.raises(ValueError, match="工号"):
            StaffId("X12345")

    def test_email_invalid_format(self) -> None:
        with pytest.raises(ValueError, match="邮箱"):
            Email("not-an-email")

    def test_email_with_nul_rejected(self) -> None:
        with pytest.raises(ValueError, match="控制字符"):
            Email("n\x00x@stu.edu.cn")

    def test_email_with_lone_surrogate_rejected(self) -> None:
        with pytest.raises(ValueError, match="代理字符"):
            Email("\ud800@x.cn")

    def test_student_id_with_nul_rejected(self) -> None:
        with pytest.raises(ValueError, match="控制字符"):
            StudentId("123\x00456")

    def test_password_hash_rejects_plaintext(self) -> None:
        with pytest.raises(ValueError, match="bcrypt"):
            PasswordHash("PlainPassword1")


class TestUserRegistration:
    def test_register_student(self) -> None:
        user = User.register(
            role="student",
            email_value="zhang@stu.edu.cn",
            password_hash_value="$2b$12$abcdefghijklmnopqrstuv",
            identity_value="2025010101",
        )
        assert user.student_id is not None and user.student_id.value == "2025010101"
        assert user.staff_id is None
        assert user.role == "student"
        assert user.events and user.events[0].user_id == user.id
        assert user.events[0].role == "student"

    def test_register_teacher(self) -> None:
        user = User.register(
            role="teacher",
            email_value="li@edu.cn",
            password_hash_value="$2b$12$abcdefghijklmnopqrstuv",
            identity_value="T10086",
        )
        assert user.staff_id is not None and user.staff_id.value == "T10086"
        assert user.student_id is None
        assert user.events[0].role == "teacher"

    def test_student_requires_student_id(self) -> None:
        with pytest.raises(IdentityRequiredError):
            User.register(
                role="student",
                email_value="zhang@stu.edu.cn",
                password_hash_value="$2b$12$abcdefghijklmnopqrstuv",
                identity_value=None,
            )

    def test_teacher_requires_staff_id(self) -> None:
        with pytest.raises(IdentityRequiredError):
            User.register(
                role="teacher",
                email_value="li@edu.cn",
                password_hash_value="$2b$12$abcdefghijklmnopqrstuv",
                identity_value=None,
            )
