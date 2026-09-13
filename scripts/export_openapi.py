"""导出 OpenAPI 契约：python scripts/export_openapi.py [--check]

- 默认：生成仓库根 openapi.json（UTF-8 无 BOM、LF 换行、indent=2）
- --check：内存重新生成并与仓库文件比对（CRLF 归一化后），不一致 exit 1
  （CI 防漂移门禁：API 变更后忘记重跑导出 → CI 红；依赖升级改变 schema 同样触发）

create_app() 无数据库连接副作用（engine 懒连接），本脚本无需任何服务即可运行。
脚本从任意工作目录运行均可（REPO_ROOT 已注入 sys.path）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = REPO_ROOT / "openapi.json"
# python scripts/export_openapi.py 时 sys.path[0] 是 scripts/ 而非仓库根，
# 手动注入才能 import app.main（python -m 运行时无此问题，双保险）
sys.path.insert(0, str(REPO_ROOT))


def generate() -> str:
    """生成 openapi JSON 文本（导出与 --check 共用同一函数，保证尾换行等完全一致）。"""
    from app.main import create_app

    schema = create_app().openapi()
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    generated = generate()

    if "--check" in sys.argv[1:]:
        try:
            committed = OPENAPI_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(
                "契约文件不存在（openapi.json）：请先运行 python scripts/export_openapi.py 导出。",
                file=sys.stderr,
            )
            return 1
        # Windows autocrlf checkout 出 CRLF：比对前归一化，避免本地假阳性
        if committed.replace("\r\n", "\n") != generated:
            print(
                "openapi.json 与当前代码不一致：API 有变更但未重新导出。\n"
                "修复：python scripts/export_openapi.py",
                file=sys.stderr,
            )
            return 1
        print("openapi.json 与当前代码一致")
        return 0

    OPENAPI_PATH.write_text(generated, encoding="utf-8", newline="\n")
    paths = json.loads(generated)["paths"]
    operations = sum(len(ops) for ops in paths.values())
    print(f"openapi.json 已导出：{OPENAPI_PATH}（{len(paths)} paths / {operations} operations）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
