"""共享文本字符校验：入库/回显前拒绝危险字符（修复暴力测试 P-01~P-03）。

两类问题字符：
- C0 控制字符（U+0000~U+001F）：PostgreSQL text/varchar 无法存储 NUL 等，
  asyncpg 抛 CharacterNotInRepertoireError，漏到路由外即 500；
  仅放行多行文本必需的 \\t \\n \\r。
- UTF-16 代理码位（U+D800~U+DFFF）：lone surrogate 无法编码 UTF-8，
  一旦回显进 JSON 响应体即 UnicodeEncodeError。

纯标准库、无框架依赖，domain 值对象与 interfaces schema 均可调用（共享内核）。
DEL（U+007F）/ C1（U+0080~U+009F）可存储可编码，显示层风险归前端，不在此拒绝。
"""

from __future__ import annotations

# 放行的空白控制字符：制表、换行、回车（多行正文的合法输入）
_ALLOWED_CONTROL_CHARS = frozenset("\t\n\r")


def reject_unsafe_text(value: str, *, field_name: str = "文本") -> None:
    """检查危险字符，命中即抛 ValueError（由路由既有 422 映射承接）。"""
    for ch in value:
        code = ord(ch)
        if code < 0x20 and ch not in _ALLOWED_CONTROL_CHARS:
            raise ValueError(f"{field_name}含不可见控制字符（U+{code:04X}），请删除后重试")
        if 0xD800 <= code <= 0xDFFF:
            raise ValueError(f"{field_name}含非法 Unicode 代理字符（U+{code:04X}），请删除后重试")
