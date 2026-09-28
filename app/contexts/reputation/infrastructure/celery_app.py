"""Celery 应用（分支 4，US-REP01）：声誉事件消费方。

broker 取 settings.celery_broker_url（默认 redis db1，与身份 refresh token 的
db0 隔离）。本地运行（Windows 必须 --pool=solo）：

    celery -A app.contexts.reputation.infrastructure.celery_app worker --pool=solo -l info

CI 无 services（D3 处置）：单测以 task_always_eager 直调（不触 broker）；
worker 真实链路由第十二路暴力测试在本地验证（台账留档）。
"""

from __future__ import annotations

from celery import Celery

from app.config.settings import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    # include= 让 worker 进程加载任务模块——celery_app 本身不 import tasks
    # （tasks 反向 import 本模块，直接 import 会成环）；漏掉它 worker 会领到
    # 消息却报 unregistered task 错误（第十二路开工前自查发现）
    app = Celery(
        "campusoverflow",
        broker=settings.celery_broker_url,
        include=["app.contexts.reputation.infrastructure.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        # 消费侧至少一次：worker 崩溃未 ack 的消息重投；记账幂等由
        # (source, event_id) 唯一索引兜底（v3.1 必修项 3）
        task_acks_late=True,
        # 消除 Celery 5.4+ 启动告警（显式声明启动期重试语义）
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = create_celery_app()
