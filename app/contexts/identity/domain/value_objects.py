from __future__ import annotations

import re
from dataclasses import dataclass

from app.shared.text_validation import reject_unsafe_text

_STUDENT_ID_PATTERN = re.compile(r"^\d{8,12}$")
_STAFF_ID_PATTERN = re.compile(r"^T\d{4,8}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class StudentId:
    """学号：8~12 位数字，全局唯一。"""

    value: str

    def __post_init__(self) -> None:
        reject_unsafe_text(self.value, field_name="学号")
        if not _STUDENT_ID_PATTERN.match(self.value):
            raise ValueError(f"学号格式不合法：{self.value!r}（应为 8~12 位数字）")


@dataclass(frozen=True, slots=True)
class StaffId:
    """工号：T 开头 + 4~8 位数字，全局唯一。"""

    value: str

    def __post_init__(self) -> None:
        reject_unsafe_text(self.value, field_name="工号")
        if not _STAFF_ID_PATTERN.match(self.value):
            raise ValueError(f"工号格式不合法：{self.value!r}（应为 T+4~8 位数字）")


@dataclass(frozen=True, slots=True)
class Email:
    """邮箱：基础格式校验，全局唯一。"""

    value: str

    def __post_init__(self) -> None:
        reject_unsafe_text(self.value, field_name="邮箱")
        if not _EMAIL_PATTERN.match(self.value):
            raise ValueError(f"邮箱格式不合法：{self.value!r}")


@dataclass(frozen=True, slots=True)
class PasswordHash:
    """密码哈希：只接受 bcrypt 形态，禁止明文（不变式 1）。"""

    value: str

    def __post_init__(self) -> None:
        if not self.value.startswith("$2"):
            raise ValueError("密码必须以 bcrypt 哈希存储，禁止明文")
