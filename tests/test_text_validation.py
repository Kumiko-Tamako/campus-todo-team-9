"""共享字符校验工具单元测试（纯 Python，进 CI；修复暴力测试 P-01~P-03）。"""

from __future__ import annotations

import pytest

from app.shared.text_validation import reject_unsafe_text


class TestRejectUnsafeText:
    @pytest.mark.parametrize(
        "safe",
        [
            "普通中文标题",
            "emoji 🔥 与 RTL 混排",
            "多行\n正文\t带\r回车",
            "a" * 100,
            "\x7f",  # DEL 可存储可编码，显示层归前端，不在此拒绝
        ],
    )
    def test_safe_text_passes(self, safe: str) -> None:
        reject_unsafe_text(safe)  # 不抛即通过

    @pytest.mark.parametrize("bad", ["\x00", "a\x00b", "\x01", "\x1f", "\x07"])
    def test_control_chars_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match="控制字符"):
            reject_unsafe_text(bad, field_name="测试字段")

    @pytest.mark.parametrize("bad", ["\ud800", "\udfff", "x\ud800y"])
    def test_surrogates_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match="代理字符"):
            reject_unsafe_text(bad)

    def test_newline_tab_carriage_return_allowed(self) -> None:
        reject_unsafe_text("line1\nline2\tend\rdone")  # 多行正文的合法空白
