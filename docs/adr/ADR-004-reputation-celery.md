# ADR-004: 声誉异步记账与首次引入 Celery（发布时机 + 幂等 + worker 数据库策略）

- 状态：已接受
- 日期：2026-09-28
- 关联阶段：阶段 3 分支 4（3.6 声誉 + Celery，迭代 4 后半）
- 证据：[3.6-reputation.md](../test/3.6-reputation.md)（门禁 + 第十二路暴力测试全量数据）

## 背景

US-REP01/REP02（Gherkin 功能域 11）要求投票/采纳触发声誉按规则异步记账且不阻塞主流程（aggregates.md 协作表"投票计入声誉：事件异步订阅，Ledger 以 event_id 幂等记账"）。分支 1/2 已随行为发出 `VoteCast`/`AnswerAccepted` 领域事件（用例代发留位），但**无任何发布机制**——本分支首次引入 Celery 作为消费方，须裁定：发布时机、幂等口径、worker 数据库访问策略、CI 无 services 处置。

## 决策

1. **发布机制：BackgroundTasks 提交后发布（at-most-once）+ 消费侧至少一次**
   - qa 路由收集用例返回的事件 → FastAPI `BackgroundTasks` 内 `task.delay(payload)`。时机依据：`scope="function"` 下 `get_session` 退出代码（commit）在响应**发送前**执行，BackgroundTasks 在响应**发送后**执行 → 发布时数据已落库（第十二路 R-07 实证，结算延迟 avg 0.41s / max 1.33s）；
   - 已知后果（如实接受）：进程在 commit 与 publish 之间崩溃、或 broker 不可达时 `delay` 抛错——事件**静默丢失**（发布失败仅记日志）。发布侧 at-most-once 是 Bloom 式取舍：outbox 表 + relay 可达 at-least-once，留阶段 4 演进；
   - 消费侧 `task_acks_late=True`：worker 崩溃未 ack 消息重投（R-08 实证停机积压恢复排空）。
2. **事件载荷自足（D-A'(i)）**：`VoteCast` +`target_author_id`（`_target_exists` 本就加载完整聚合，改提作者）；`AnswerAccepted` +`event_id`（uuid4，采纳事务内生成一次）。worker 记账**零查 qa 库**，无"目标已删→重试"路径；reputation 上下文对 qa 0 import（事件经 DTO dict 进入）。
3. **幂等口径：`(source, event_id)` 复合唯一索引 + ON CONFLICT DO NOTHING**
   - vote 侧 event_id=票行主键 `vote_id`（不可改票，复投 409→一票一键）；accept 侧=事件 `event_id`；两异源 UUID 以 `source`（String(8)）隔离语义；
   - 仓储用 PG `INSERT … ON CONFLICT … DO NOTHING + RETURNING`：原子判定、无异常抛出（排除 acks_late 下"报错→重投"循环）、无 rowcount 类型妥协；`RETURNING` 空结果即判重命中。
4. **worker 数据库策略：专用 NullPool 引擎（强制，无视 `db_pool_size` 配置）**
   - 任务体内 `asyncio.run()` 每次新建事件循环；池化连接绑定创建它的 loop，跨任务复用必挂（"attached to a different loop"）。NullPool 不持有连接，对多 loop 免疫（与 engine.py 默认路径同源决策）；worker 记账量小，每任务新建连接可接受（R-10 日志净检零跨 loop 错误）；
   - 引擎对象进程内缓存（NullPool 引擎本身无连接，跨 loop 安全）；connect_args 沿用 5s 建连超时与 statement/lock timeout。
5. **重试口径**：瞬态错误（`SQLAlchemyError`/`asyncpg.PostgresError`/`OSError`/内置 `TimeoutError`）→ `autoretry_for` + 退避（backoff 60s 上限 + jitter，max 5 次）；载荷非法（未知 target/direction，应用层 `ValueError`）→ 不重试，失败即弃（毒消息防循环）。
6. **CI 无 services 处置（D3）**：CI 不跑 worker/Redis；单元测试直调记账函数（fake 仓储）；API 集成测试以 `task_always_eager=True` 走真实任务体（不触 broker）；真实 worker 链路由第十二路在本地验证。
7. **任务注册**：`Celery(include=["app.contexts.reputation.infrastructure.tasks"])`——celery_app 不 import tasks（tasks 反向 import 本模块会成环），漏掉 include 的 worker 会领到消息却报 unregistered task（开工前自查发现并修复，R-10 实证）。

## 记分口径（唯一出处：`reputation/domain/ledger.py` 常量）

| 事件 | 被记用户 | delta |
|:--|:--|:--|
| 回答被赞 | 回答作者 | +10 |
| 回答被踩 | 回答作者 | −2 |
| 问题被赞 | 提问者 | +5 |
| 问题被踩 | 提问者 | −2 |
| 被采纳 | 回答作者 | +15 |

自投（actor == 被记用户）不计分（跳过即成功，非错误）；不引入"踩人者扣分"（SO 全量规则简化，v3.1 裁定 3）。账面总值 = 流水累加（不落总值列，`SUM` 现算），可为负。

## 实测结果

- 门禁：pytest **254 passed**（232 既有 + 22 新增，既有零适配）/ ruff 0 / mypy 83 文件 0 / coverage TOTAL 79.26%（≥70）/ domain 95%（≥90）/ openapi 16 paths / 17 ops 过 `--check`；
- 第十二路暴力测试（bruteforce_44，真实 :8001 实例 + 真实 solo worker）：**11/11 PASS**——记分矩阵对账、结算延迟 avg 0.41s/max 1.33s、自投跳过、复投 409 不加行、重复采纳仅一条、同事件双投递恰一行、停机积压恢复排空（B 33→43 / A 5→8 精确吻合）、GET 滥用 401/403/422、worker 日志净检零异常。

## 后果与遗留

- **正向**：投票/采纳主流程零阻塞（发布在响应后）；重复投递/重放/worker 崩溃恢复均幂等安全；上下文边界干净（reputation 对 qa 0 import，发布经单模块公开供给面）。
- **遗留（如实）**：
  1. 发布侧 at-most-once 窗口——进程崩溃/broker 宕机丢事件（日志可观测、不重放）。课程规模接受；阶段 4 若需严格不丢，演进 outbox 表 + relay；
  2. `ReputationChanged` 事件已定义不派发（无订阅者，通知/排行归后续迭代）；
  3. 多 worker 并发同事件的双投递竞争由唯一索引兜底（单 worker 链路已验证；双 worker 并发消费未单独压测，索引层面数学上安全）；
  4. Windows 本地 worker 须 `--pool=solo`（prefork 不可用）；生产 Linux 部署配置归阶段 4。
