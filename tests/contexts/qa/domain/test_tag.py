"""Tag 值对象与 TagCatalog 聚合单元测试：纯 domain，无框架（进 CI）。"""

from __future__ import annotations

import pytest

from app.contexts.qa.domain.tag import Tag, TagCatalog


class TestTagValueObject:
    def test_strips_and_normalizes(self) -> None:
        assert Tag("  数据库 ").value == "数据库"

    def test_rejects_empty_after_strip(self) -> None:
        with pytest.raises(ValueError, match="1~50 字"):
            Tag("   ")

    def test_rejects_over_50_chars(self) -> None:
        with pytest.raises(ValueError, match="1~50 字"):
            Tag("长" * 51)

    def test_accepts_50_chars(self) -> None:
        assert len(Tag("长" * 50).value) == 50

    def test_allows_cjk_letters_digits_hyphen_underscore_space(self) -> None:
        for value in ("数据库", "SQL", "cs-lab", "ai_2025", "机器学习 入门", "123"):
            assert Tag(value).value == value

    def test_rejects_emoji_and_symbols(self) -> None:
        for value in ("标签🔥", "a#b", "c+d", "e<f>", "g|h"):
            with pytest.raises(ValueError, match="不支持的字符"):
                Tag(value)

    def test_rejects_control_and_surrogate(self) -> None:
        with pytest.raises(ValueError, match="不支持的字符"):
            Tag("a\u0001b")
        with pytest.raises(ValueError, match="不支持的字符"):
            Tag("a\u200bb")  # 零宽空格（Cf）

    def test_key_is_lower(self) -> None:
        assert Tag("SQL").key == "sql"
        assert Tag("数据库").key == "数据库"

    def test_key_folds_final_sigma(self) -> None:
        """第十路 U-05 回归：ς 与 σ caseless 等价 → 同键归并；定向折叠不外溢。"""
        assert Tag("ΟΔΟΣ").key == Tag("οδος").key  # 词尾 Σ→ς 与显式 ς/σ 同键
        assert Tag("οδος").key == Tag("οδοσ").key  # ς(U+03C2) → σ(U+03C3)
        assert Tag("ß").key == "ß"  # 不 casefold：ß 保持自身（≠ "SS".key）
        assert Tag("ß").key != Tag("SS").key

    def test_fullwidth_not_folded(self) -> None:
        """v6 定稿：不做 NFKC——全角Ａ ≠ 半角A，是两个不同标签。"""
        assert Tag("Ａ").key != Tag("A").key

    def test_strip_removes_fullwidth_and_nbsp_edges(self) -> None:
        """第十路 U-02/U-03 定口径：首尾 U+3000/NBSP 被 Unicode strip 清理后归并（非 422）。"""
        assert Tag("\u3000SQL\u3000").value == "SQL"
        assert Tag("\u00a0SQL\u00a0").value == "SQL"
        assert Tag("\u3000SQL\u3000").key == Tag("SQL").key

    def test_interior_fullwidth_or_nbsp_rejected(self) -> None:
        """内部空白仅允许 U+0020：全角空格/NBSP 在中间 → 白名单拒（U-04）。"""
        with pytest.raises(ValueError, match="不支持的字符"):
            Tag("S\u3000QL")
        with pytest.raises(ValueError, match="不支持的字符"):
            Tag("S\u00a0QL")


class TestTagCatalog:
    def test_resolve_dedupes_case_insensitive(self) -> None:
        catalog = TagCatalog()
        tags = catalog.resolve(["SQL", "sql", "Sql"])
        assert [t.value for t in tags] == ["SQL"]

    def test_resolve_keeps_first_seen_order(self) -> None:
        catalog = TagCatalog()
        tags = catalog.resolve(["数据库", "AI", "数据库"])
        assert [t.value for t in tags] == ["数据库", "AI"]

    def test_resolve_rejects_six_unique(self) -> None:
        catalog = TagCatalog()
        with pytest.raises(ValueError, match="至多 5 个标签"):
            catalog.resolve(["a1", "b2", "c3", "d4", "e5", "f6"])

    def test_resolve_counts_after_dedupe(self) -> None:
        """6 个原始串去重后 5 个 → 合法（1.3 功能域 10 上限按去重后计）。"""
        catalog = TagCatalog()
        tags = catalog.resolve(["A", "a", "b", "c", "d", "e"])
        assert len(tags) == 5

    def test_resolve_empty_ok(self) -> None:
        assert TagCatalog().resolve([]) == []
