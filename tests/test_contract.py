"""OpenAPI 契约测试（不连库，进 CI）——步骤 3.7 交付物①。

三个维度：
- 防漂移：复用 scripts/export_openapi.py 的 generate() 单源（X-06 教训：
  不重写序列化逻辑），与仓库 openapi.json 比对，等价于把 CI `--check` 门禁
  升格为本地 pytest 资产；
- 完整性：paths/operations 计数、operationId 全局唯一、四族功能路径齐备
  （auth / questions / answers-votes-accept-comments / tags+reputation）；
- 约定：/health 归 ops 标签、securitySchemes 含 bearer 方案。

运行时 422 响应形态不在本文件重复断言——已由
tests/test_validation_handlers.py 覆盖（P-01~P-04），此处只守契约文档本身。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = REPO_ROOT / "openapi.json"
EXPORT_SCRIPT = REPO_ROOT / "scripts" / "export_openapi.py"

# 四族功能路径（阶段 2-3 交付的全部 API 面）
_FAMILIES: dict[str, list[str]] = {
    "auth": [
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
    ],
    "qa": [
        "/api/v1/questions",
        "/api/v1/questions/{question_id}",
        "/api/v1/questions/{question_id}/answers",
        "/api/v1/questions/{question_id}/vote",
        "/api/v1/questions/{question_id}/answers/{answer_id}/vote",
        "/api/v1/questions/{question_id}/close",
        "/api/v1/questions/{question_id}/comments",
        "/api/v1/answers/{answer_id}/comments",
        "/api/v1/answers/{answer_id}/accept",
    ],
    "tags": ["/api/v1/tags"],
    "reputation": ["/api/v1/users/{user_id}/reputation"],
}

_METHODS = ("get", "post", "put", "patch", "delete")


def _schema() -> dict[str, Any]:
    return json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return _schema()


def _load_generate():  # type: ignore[no-untyped-def]
    """按路径加载 scripts/export_openapi.py，取其 generate()（单源复用）。"""
    spec = importlib.util.spec_from_file_location("export_openapi", EXPORT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.generate


class TestContractDrift:
    """① 防漂移：仓库 openapi.json 必须与当前代码生成结果一致。"""

    def test_openapi_json_matches_generated(self) -> None:
        generate = _load_generate()
        # Windows autocrlf checkout 出 CRLF：与 export 脚本 --check 同款归一化
        committed = OPENAPI_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert committed == generate(), (
            "openapi.json 与当前代码不一致：API 有变更但未重新导出。"
            "修复：python scripts/export_openapi.py"
        )


class TestContractCompleteness:
    """② 完整性：计数、operationId 唯一、四族路径齐备。"""

    def test_path_and_operation_counts(self, schema: dict[str, Any]) -> None:
        paths: dict[str, Any] = schema["paths"]
        operations = [
            (path, method)
            for path, item in paths.items()
            for method in item
            if method in _METHODS
        ]
        assert len(paths) == 17, f"paths 数量漂移：期望 17，实际 {len(paths)}"
        assert len(operations) == 19, f"operations 数量漂移：期望 19，实际 {len(operations)}"

    def test_operation_ids_unique(self, schema: dict[str, Any]) -> None:
        ids = [
            item[method].get("operationId")
            for item in schema["paths"].values()
            for method in item
            if method in _METHODS
        ]
        assert all(ids), f"存在缺失 operationId 的操作：{ids}"
        duplicates = {i for i in ids if ids.count(i) > 1}  # type: ignore[arg-type]
        assert not duplicates, f"operationId 重复：{duplicates}"

    def test_all_four_families_present(self, schema: dict[str, Any]) -> None:
        declared = set(schema["paths"])
        for family, expected in _FAMILIES.items():
            missing = [p for p in expected if p not in declared]
            assert not missing, f"{family} 族路径缺失：{missing}"


class TestContractConventions:
    """③ 约定：/health 标签与鉴权方案。"""

    def test_health_tagged_ops(self, schema: dict[str, Any]) -> None:
        assert schema["paths"]["/health"]["get"]["tags"] == ["ops"]

    def test_bearer_security_scheme(self, schema: dict[str, Any]) -> None:
        schemes = schema["components"]["securitySchemes"]
        bearer = [s for s in schemes.values() if s.get("scheme") == "bearer"]
        assert bearer, f"securitySchemes 缺少 bearer 方案：{list(schemes)}"
