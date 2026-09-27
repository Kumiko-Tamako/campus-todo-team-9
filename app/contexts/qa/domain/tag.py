from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from uuid import UUID

_TAG_MIN_LENGTH = 1
_TAG_MAX_LENGTH = 50
_MAX_TAGS_PER_QUESTION = 5

# 标签白名单字符：中英文（Lo/Lu/Ll）、数字、连字符、下划线、空格（U+0020）。
# 其余符号/emoji/控制字符一律拒绝——标签是目录键，收窄字符集防注入与显示混乱。
_ALLOWED_CATEGORIES = frozenset({"Lo", "Lu", "Ll", "Nd"})

# 归并键定向折叠：希腊词尾 sigma ς(U+03C2) → 词中 σ(U+03C3)。
# 第十路 U-05 实证：二者 Unicode caseless 等价（同一希腊词的两种合法拼写），
# 而 str.lower() 不做此折叠 → 同词两行目录。**不用 casefold()**：casefold 附带
# ß→ss、ﬀ→ff 等展开，会把"ß"与"SS"判为同名（白名单显示名语义被破坏）；
# 此处只定向闭合 σ/ς 这一个跨大小写变体族（İ 族已由 key 列单源修复，X-06）。
_FINAL_SIGMA_FOLD = str.maketrans("\u03c2", "\u03c3")


def _is_allowed_char(ch: str) -> bool:
    if ch in ("-", "_", " "):
        return True
    return unicodedata.category(ch) in _ALLOWED_CATEGORIES


@dataclass(frozen=True, slots=True)
class Tag:
    """标签值对象：strip 规范化后 1~50 字（Unicode 码点数），白名单字符。

    - 规范化：`strip()` 为 Unicode 感知——首尾全角空格（U+3000）、NBSP（U+00A0）等
      一律清理后按剩余内容校验/归并（第十路 U-02/U-03 定口径：**清理归并，非 422**）；
      **内部**空白仅允许 U+0020（全角空格/NBSP 在中间 → 白名单拒 422，U-04）。
    - 大小写不敏感唯一（T02）：归并键 = `lower()` + 词尾 σ 定向折叠，
      **应用单侧计算并落 tags.key 列**（单一事实源；X-06 教训：PG lower 与 Python
      lower 对个别码位映射不同，表达式索引会成死路。全角≠半角：不做 NFKC，v6 定稿）。
    - 非法字符/长度越界 → ValueError（中文消息，路由 422 字符串形承接；
      消息不回显标签值——lone surrogate 回显即 P-02 族 500）。
    - id 由目录持久化时填充（get-or-create 返回带 id 的实例）；构造时恒 None，
      值语义仍以 value 为准。
    """

    value: str
    id: UUID | None = None

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not (_TAG_MIN_LENGTH <= len(normalized) <= _TAG_MAX_LENGTH):
            raise ValueError(
                f"标签需 {_TAG_MIN_LENGTH}~{_TAG_MAX_LENGTH} 字（去首尾空白后），"
                f"实际 {len(normalized)} 字"
            )
        for ch in normalized:
            if not _is_allowed_char(ch):
                code = ord(ch)
                raise ValueError(
                    f"标签含不支持的字符（U+{code:04X}）："
                    "仅允许中英文、数字、连字符、下划线与空格"
                )
        object.__setattr__(self, "value", normalized)

    @property
    def key(self) -> str:
        """同名归并键：lower + ς→σ 定向折叠（应用单源，落 tags.key 列）。"""
        return self.value.lower().translate(_FINAL_SIGMA_FOLD)


@dataclass(slots=True)
class TagCatalog:
    """TagCatalog 聚合根：全局标签目录，持本事务内已知的 Tag 集合（T01/T02）。

    目录的持久化唯一性（tags.key 列唯一索引）由基础设施层兜底；
    本聚合负责"随用随建 + 同名归并"的内存语义（Q03 合法性校验源）。
    """

    tags: dict[str, Tag] = field(default_factory=dict)  # key → Tag（首见显示名）

    def register(self, tag: Tag) -> Tag:
        """登记一个标签：同名（归并键，见 Tag.key）命中，返回目录内规范项。"""
        existing = self.tags.get(tag.key)
        if existing is not None:
            return existing
        self.tags[tag.key] = tag
        return tag

    def resolve(self, values: list[str]) -> list[Tag]:
        """把原始标签串解析为目录内 Tag 列表：去重（按归并键）→ 数量上限校验（Q03）。

        顺序 = 去重后首见顺序；超过 5 个 → ValueError（中文消息 → 422）。
        """
        resolved: list[Tag] = []
        seen: set[str] = set()
        for raw in values:
            tag = self.register(Tag(raw))
            if tag.key not in seen:
                seen.add(tag.key)
                resolved.append(tag)
        if len(resolved) > _MAX_TAGS_PER_QUESTION:
            raise ValueError(
                f"至多 {_MAX_TAGS_PER_QUESTION} 个标签（同名标签自动归并后计数），"
                f"实际 {len(resolved)} 个"
            )
        return resolved
