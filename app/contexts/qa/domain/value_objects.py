from __future__ import annotations

from dataclasses import dataclass

from app.shared.text_validation import reject_unsafe_text

_TITLE_MIN_LENGTH = 1
_TITLE_MAX_LENGTH = 100
_BODY_MIN_LENGTH = 1
_BODY_MAX_LENGTH = 5000


@dataclass(frozen=True, slots=True)
class Title:
    """问题标题：自由文本，strip 规范化后 1~100 字（首尾空白视为误输入）。"""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        reject_unsafe_text(normalized, field_name="标题")
        if not (_TITLE_MIN_LENGTH <= len(normalized) <= _TITLE_MAX_LENGTH):
            raise ValueError(
                f"标题需 {_TITLE_MIN_LENGTH}~{_TITLE_MAX_LENGTH} 字（去首尾空白后），"
                f"实际 {len(normalized)} 字"
            )
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class Body:
    """问题正文：自由文本，strip 规范化后 1~5000 字。"""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        reject_unsafe_text(normalized, field_name="正文")
        if not (_BODY_MIN_LENGTH <= len(normalized) <= _BODY_MAX_LENGTH):
            raise ValueError(
                f"正文需 {_BODY_MIN_LENGTH}~{_BODY_MAX_LENGTH} 字（去首尾空白后），"
                f"实际 {len(normalized)} 字"
            )
        object.__setattr__(self, "value", normalized)
