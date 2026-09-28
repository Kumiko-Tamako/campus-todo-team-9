"""声誉事件发布面（reputation 公开供给面，v3.1 D-B）。

qa interfaces 仅 import 本模块发布事件（不触 reputation 内部基础设施）；
reputation 不 import qa——载荷以 JSON 安全 dict 传递，事件序列化由 qa 侧完成。

发布时机（D-B 选型）：BackgroundTasks 在响应发送后执行，而 scope="function" 下
get_session 退出代码（commit）在响应发送前完成——故 apply_async 执行时数据已落库
（发布时序探针 R-07 实证）。发布失败（broker 不可达等）只记日志：已知的
at-most-once 窗口，ADR-004 登记其后果与阶段 4 演进方向（outbox）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import BackgroundTasks

from app.contexts.reputation.infrastructure.tasks import (
    apply_accept_bonus,
    apply_vote_delta,
)

logger = logging.getLogger(__name__)


def _publish(task: Any, payload: dict[str, Any]) -> None:
    """BackgroundTasks 执行体：delay 失败仅记日志（响应已发出，事件丢失可容忍）。"""
    try:
        task.delay(payload)
    except Exception:
        logger.exception(
            "声誉事件发布失败（at-most-once 窗口，ADR-004）: task=%s payload=%s",
            task.name,
            payload,
        )


def publish_vote_event(background_tasks: BackgroundTasks, payload: dict[str, Any]) -> None:
    """投递投票事件（reputation.apply_vote_delta）。"""
    background_tasks.add_task(_publish, apply_vote_delta, payload)


def publish_accept_event(background_tasks: BackgroundTasks, payload: dict[str, Any]) -> None:
    """投递采纳事件（reputation.apply_accept_bonus）。"""
    background_tasks.add_task(_publish, apply_accept_bonus, payload)
