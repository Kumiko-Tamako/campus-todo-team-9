# ADR-003: 连接池化与并发容量工程（哨兵式池 + 异常分层 + 实测口径）

- 状态：已接受（含 1 项遗留）
- 日期：2026-09-26
- 关联阶段：阶段 3 收尾（容量验收）/ 阶段 4 前置
- 证据：[3.3-accept-comments.md 第八节](../test/3.3-accept-comments.md)（基线 + 实施 + 复测全量数据）

## 背景

2026-09-26 第四路测试立起承载基线（bruteforce_35，单 uvicorn worker）：`NullPool`（每请求新建 PG 连接）+ PG `max_connections=100` 下最高可持续并发 ≈100（RPS 22-31）；150+ 即 `asyncpg.TooManyConnectionsError` 塌缩，且该异常为 asyncpg 驱动裸异常（非 `SQLAlchemyError` 子类、方言层 connect 路径不包装，F-2），绕过既有 400 兜底致裸 500。目标：承载能力提升至 1w 并发在途 SUSTAINED（零 5xx、零传输错误、零非预期 4xx）。

## 决策

1. **哨兵式连接池**（`app/config/settings.py`、`app/shared/engine.py`）：
   - `db_pool_size=0`（默认）为哨兵 → 沿用 `NullPool`（保 pytest 多事件循环免疫、测试/CI 零影响）；**0 绝不传入池**——SQLAlchemy 语义 `pool_size=0` 为无上限池（`max_overflow` 被强制 -1，SQLAlchemy impl.py L139），会复现连接风暴；
   - `db_pool_size>0` → `AsyncAdaptedQueuePool(pool_size, max_overflow, pool_timeout=10, pool_pre_ping=True, pool_recycle=1800)`；单进程连接上限 = `pool_size + db_max_overflow`；
   - 部署不变式：`workers × (pool_size + max_overflow) ≤ max_connections − 余量`。
2. **数据库异常分层兜底**（`app/shared/exception_handlers.py`、`app/main.py`）：
   - asyncpg 两条平行根（`PostgresError` / `InterfaceError`，无公共基类）→ 503（连接建立路径原始异常，F-2 修复）；
   - `sqlalchemy.exc.TimeoutError`（池排队超限）→ 503（防御语义，压测触发即容量不足）；
   - `sqlalchemy.exc.DBAPIError` → 分流 handler：`IntegrityError/DataError/ProgrammingError` 沿用 400 兜底，其余（连接类/泛型）→ 503（覆盖执行路径——asyncpg `PostgresError` 经方言翻译为类名 "Error"，最终落泛型 `DBAPIError`，故注册该基类 + isinstance 分流）；
   - 既有 `SQLAlchemyError → 400` 保留（非 DBAPIError 的 sqlalchemy 异常）。
3. **基础设施**（`docker-compose.yml`）：PG `max_connections=100→400`、`shared_buffers=256MB`（按不变式容纳 4 workers × (20+30) = 200）。

## 实测结果（本机 Windows 16 逻辑核 + Docker Desktop；raw asyncio 压测客户端，混合读写闭环）

| 配置 | 最高可持续并发 | 关键数字 |
|:---|:---|:---|
| 基线：NullPool + max_connections=100 | ≈100 | RPS 22-31；150+ 塌缩 + 裸 500 |
| 单 worker + 池 20/30 | **562** | RPS 142-159；606 档起池排队超 10s → 503（预期防御语义） |
| 4 workers + 池 20/30 | 100-250 档可达（RPS 361-424）；300 档起不稳 | 见遗留 1 |
| 单 worker + 池 20/30 + `pool_timeout=120` + backlog=16384 + pre-connect（二轮复测） | **5000 ✅ / 8000 ✅ / 10000 ✅** | RPS 240-374；p99 45.8-107.4s（排队，如实） |

- **1w 目标达成（二轮口径）**：以排队容忍度杠杆（`pool_timeout` 10→120s）+ **pre-connect 分批预建连**（化解 10k 同时建连的 SYN 风暴）+ `--backlog 16384`，**10000 并发在途 SUSTAINED**（零 5xx/零传输/零超时/零 4xx；延迟 p99 ~107s 为排队深度如实反映）。瓶颈本质仍为单请求 ~7ms 服务端处理——并发数 ≈ 吞吐 × 排队容忍度，非池、非 PG（pgmax 恒 51）。
- 池化收益（单 worker 100 档）：RPS 22 → 142（≈6.5×）；最高可持续并发 100 → 562（≈5.6×，初测口径）。

## 后果与遗留

- **正向**：PG 连接风暴消除（单 worker pgmax ≤51、4 workers ≤201，与池上限精确对应）；容量提升 5-6 倍；连接类故障由裸 500 变为语义化 503（可重试）；池为显式配置项，默认路径（测试/CI）零影响。
- **遗留（如实，详见台账第八节）**：
  1. **多 worker 30s 级偶发挂起**：仅多 worker、仅业务请求（100 档首轮 29/8425、300 档 70-100 个）；同时段独立探针（直连同链路 asyncpg）62-111ms 全程健康、PG 侧 idle、4 worker 存活 → 非 DB/网络链路问题，未定位到产品代码原因。按"Windows 多 worker 实证失败"降级：终测采用单 worker 口径；生产（Linux 容器直连拓扑）需复验。
  2. **既有可见性窗口（非本轮引入）**：FastAPI ≥0.106 起 yield 依赖 teardown 在响应发送后执行（`get_session` 的 commit 随之后置）——register/question 201 与提交间存在亚秒窗口，立即级联操作（login/子资源创建）可能 401/404。**已于 2026-09-26 实施修复**：全部 13 处使用点声明 `Depends(get_session, scope="function")`（退出代码在响应数据生成后、发送前执行，commit 先于响应返回）；双实证：注册后亚毫秒立即登录 20/20 全 200、压测 `VISIBILITY_RETRIES=0`，见 PROGRESS 变更记录。
  3. 测试方法学：httpx 单进程 CPU ~12ms/请求（~90 RPS 天花板）为测量伪影，已换 raw asyncio keep-alive（~0.26ms/请求）；Docker Desktop 端口转发建连 50-400ms 且负载下劣化，复测改用直连 Docker VM IP（更接近生产容器同网拓扑）；冲顶阶段以 **pre-connect 两阶段（分批预建连）+ 轮间 TIME_WAIT 冷却**保障测量干净（详见台账 8.4）。

## 关联

- 基线证据：[docs/test/3.3-accept-comments.md](../test/3.3-accept-comments.md) 第八节
- 压测工具：`D:\a_work\bruteforce_35_load.py`（仓库外；raw 传输层 + 可见性重试）