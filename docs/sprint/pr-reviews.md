# PR 评审记录（阶段 3 · 步骤 3.7 交付物②）

> 说明：本仓库 11 个 PR 在 GitHub 上均无平台内 review（作者无法自评审自己的 PR，
> 队友评审在平台外进行）。本记录按**仓库内真实证据**（PROGRESS 变更记录、测试台账、
> ADR、commit diff）组装，评审方式如实标注（交叉会话审计 / 暴力测试轮 / 自审），
> 不虚构平台内评审活动。每条格式：元信息 / 评审方式 / 发现 / 处置 / 结论 / 遗留。

---

## 评审 1 — PR #15：feat/reputation（3.6 声誉 + Celery）

| 项 | 内容 |
|:--|:--|
| 元信息 | 分支 `feat/reputation`，commit `74980ff`，merge `e09c0f4`（2026-09-28），16 paths/17 ops |
| 评审方式 | 细案 v3.1 三轮跨会话审计（开工前）+ 第十二/十三路暴力测试（交付后）+ 自审 |

**发现与处置**（严重级：高/中/低）：

1. 【高】领域事件载荷不自足：`VoteCast` 原不携带被投票对象的作者 ID，reputation
   消费者需回查 qa 库才能记账，破坏上下文隔离。→ 处置：载荷补 `target_author_id`
   （`_target_exists` 改 `_target_author`）、`AnswerAccepted` 补 `event_id`，
   reputation 对 qa 保持 0 import。
2. 【高】worker 内跨事件循环复用池化连接：Celery solo worker 每次 `asyncio.run`
   新建 loop，共享 engine 的池化连接会跨 loop 失效。→ 处置：worker 强制独立
   NullPool 引擎（ADR-004 登记），worker 日志净检零跨 loop 异常实证。
3. 【中】至少一次投递的重复记账风险：→ 处置：`task_acks_late=True` +
   `reputation_ledgers` 唯一索引 `(source, event_id)` + `ON CONFLICT DO NOTHING`
   原子幂等；同事件双投递恰一行实证。
4. 【中】发布失败语义未定：→ 处置：BackgroundTasks 提交后发布（commit 先行），
   发布失败记日志 at-most-once，写入 ADR-004。

**结论**：approve。门禁 pytest 254 passed / ruff 0 / mypy 0 / coverage 79.26%（CI
单测口径）、domain 95%；第十二路 11/11、第十三路 20/20 全 PASS。

**遗留**：声誉最终一致（结算延迟 avg 0.41s/max 1.33s），前端展示需按契约说明处理；
毒载荷防御仅第十三路 M3 覆盖，生产环境 DLQ 策略留阶段 4。

---

## 评审 2 — PR #14：feat/tags（3.5 标签目录）

| 项 | 内容 |
|:--|:--|
| 元信息 | 分支 `feat/tags`，commit `ce7280c`，merge `67cd8da`（2026-09-27），15 paths/16 ops |
| 评审方式 | v6 细案五轮收敛送审 + 第九~十一路暴力测试轮 + 自审 |

**发现与处置**：

1. 【高】X-06 归并键双实现分歧死路：Python 与 PostgreSQL 对 İ(U+0130) 的 lower
   全映射/简单映射不一致，"查不到→撞索引→重查不到"400 死路。→ 处置：归并键落
   **独立列 key（应用单源计算）**，废弃 lower(name) 表达式索引；backfill 脚本键
   同样用产品代码单源计算。教训升格为通用纪律：序列化/归一逻辑禁止双实现。
2. 【中】σ/ς 等价类缺口：lower 不做 casefold，希腊同词两行。→ 处置：定向折叠
   `ς→σ` 单字符 translate（明确**不用** casefold——ß→ss 展开破坏显示名语义）。
3. 【中】同名标签并发创建竞态：→ 处置：savepoint 兜底 get-or-create；32 路并发
   同名恒 1 行实证。
4. 【低】口径偏差：首尾 U+3000/NBSP 被 Unicode strip 清理归并，细案误写 422。
   → 处置：定口径为正式行为，docstring + 回归测试钉死。

**结论**：approve。门禁 pytest 232 passed / ruff 0 / mypy 0；第九路 9/9、第十路
零硬缺陷、第十一路 4040 请求 0×5XX 且五条库级不变式全 PASS。

**遗留**：手写迁移 `b4e91f7a2c35` 已过 down→up 往返验证；标签搜索/热度排序留迭代 5。

---

## 评审 3 — PR #13：fix/bruteforce-closure（暴力测试审查轮收口）

| 项 | 内容 |
|:--|:--|
| 元信息 | 分支 `fix/bruteforce-closure`，commit `2731577`（含 `289a001` 快照），merge `6d8bc0a`（2026-09-27） |
| 评审方式 | 第五~八路交叉会话暴力测试轮（换方法：审查性重放 / 回归核验 / 故障注入）+ 自审 |

**发现与处置**：

1. 【高】Bug-4 回归：`289a001` 条件 UPDATE 重写时丢弃了原
   `except IntegrityError→AnswerAlreadyAcceptedError` 翻译，AC-12 场景（同题不同
   答案并发抢采）从 409 退化为 400。→ 处置：恢复 try/except 翻译；第六路复测
   K-05v 恢复 1×204+7×409。**教训：重写兜底分支必须对照原语义逐分支回归。**
2. 【高】Bug-5 异常消息泄露：投票并发兜底消息嵌 `exc.orig`（asyncpg 驱动类名 +
   约束名 + DETAIL 键结构）经 409 detail 回显客户端。→ 处置：消息改固定文案；
   全库 grep 确认 `exc.orig` 泄露面清零；40 轮×16 并发探针 leak_hits=0。
3. 【中】测试夹具泄漏脏数据：`test_accepted_answer_sorts_first` 只写 answers 侧
   不写 questions 侧，每次 pytest 留 1 行不一致数据（累积 18 行）。→ 处置：夹具
   成对写入 + backfill，pytest 后复查脏数据 0。
4. 【中】故障路径状态码分层缺口（第八路故障注入 4 观察点）：无 statement/lock
   timeout（锁等待无限挂起）、22xxx DataError→400 为死分支、refresh 先消耗 Redis
   令牌后读 DB（失败烧令牌与 503 可重试契约相悖）。→ 处置：三项全修（server_settings
   下发 5s 超时；经 `orig.__cause__` 读 SQLSTATE；refresh 重排先 DB 后 GETDEL），
   探针 6/6 PASS。

**结论**：approve。门禁 pytest 201 passed / ruff 0 / mypy 0；第五~八路累计复测全过，
故障注入 9/9 零新增缺陷。

**遗留**：多态 votes/comments 无库级 FK 留 Q08；生产 Linux 环境复验容量工程副作用
（多 worker 偶发挂起）留阶段 4。

---

## 评审 4 — PR #11：chore/openapi-export（2.8 契约交付）

| 项 | 内容 |
|:--|:--|
| 元信息 | 分支 `chore/openapi-export`，merge `d7118ab`（2026-09-13），8 paths/9 ops |
| 评审方式 | 契约暴力测试 C 系列 + 第七/八路交叉会话轮（前端消费视角 / 结构合法性+CI 预演）+ 自审 |

**发现与处置**：

1. 【高→已修】K-06 `/health` 无 tags：第八路结构检查发现，ops 端点混入 default
   分组，契约消费方（前端分组导航）受影响。→ 处置：`app/main.py` 加 `tags=["ops"]`
   一行 + 重导出同步契约 + 门禁复跑全绿。
2. 【低→已修】D-01 `--check` 缺文件报错不友好：openapi.json 不存在时报栈错误。
   → 处置：补友好报错，exit 1 语义不变。
3. 【中→契约注记】422 响应 schema 比现实宽松：schema 声明含 `input`/`ctx` 字段
   但实际处理器永不含（第六路发现）。→ 处置：api-contract-notes.md 补注记，
   不改运行时行为（收紧 schema 留迭代需要时再做）。

**结论**：approve。C 系列 15/15 + 七路累计 59 例 0 真 FAIL；`generate()` 单源
导出 + CI `--check` 防漂移门禁自此生效（本次 3.7 契约测试即复用该单源）。

**遗留**：`additionalProperties`、securitySchemes 两项契约增强已在七路确认进契约；
破坏性变更（详情 answers `list[str]`→对象数组）在 3.1 兑现并提前知会前端。
