# CampusOverflow 阶段 3 执行计划（定稿版）

> 版本：v3 定稿（2026-09-22）· 状态：**已定稿，可开写**（待审 5 项已全部自裁，见第 5 节裁定结果）
> 开写纪律不变：按第 2 节六步法逐步批准执行，每步做完汇报即停
> v2 修订（对照 1.3 Gherkin 与 aggregates.md 定稿核实）：① Vote 补方向字段（1.3 L144 明确"投赞成或反对票"，非开放问题）；② 砍掉 closed_at/close() 及关闭禁答/禁投检查（aggregates.md 定稿归迭代 5 = Q08/V02，分支 1 属迭代 2，属越范围预埋）；③ VoteCast 改为分支 1 投票即发（aggregates.md L43/L56 列为聚合事件，与"无订阅者照发"模式一致），分支 4 只加消费方；④ Comment 定性由值对象改为实体（aggregates.md L17 定稿：挂宿主聚合）；⑤ 补"问题列表按投票排序"（1.3 L162-164，迭代 2 US-Q02）进分支 1；⑥ 分支 2 采纳双写注明事务边界；⑦ 改票语义按 1.3 字面解读为"不可改票"并列入待审 #5 请确认，VoteCast 由用例代发的归属偏差补注说明

## 0. 背景基线（审核前提）

- 技术栈：Python 3.12 / FastAPI / SQLAlchemy 2.0 async + Alembic / PostgreSQL 16 / Redis 7 / pytest / ruff / mypy --strict / GitHub Actions
- 架构：DDD 限界上下文纵切，物理分包 `app/contexts/{identity,qa,course,reputation,discovery}/{domain,application,infrastructure,interfaces}`；domain 层纯 Python，禁 import FastAPI/SQLAlchemy
- 阶段 2 已交付：注册 / 登录（JWT 双令牌、轮换、吊销）/ 提问 / 列表 / 详情（`GET /api/v1/questions/{id}` 的 answers 区当前恒空数组）+ `openapi.json` 契约（8 paths，CI `--check` 防漂移门禁）
- 现有 qa domain 模式：聚合根 dataclass + 工厂方法发领域事件（`Question.ask()` 发 `QuestionPublished`，无订阅者照发留位事件总线）；值对象 frozen dataclass 构造即校验；仓储为 domain Protocol + infra SQLAlchemy 实现，聚合从库重建时构造函数直填、事件不回放
- 阶段 3 目标（Lab 6+7）：回答 / 投票 / 采纳 / 评论 / 标签 / 声誉 + 首次引入 Celery；测试冲刺（覆盖率 ≥70%、核心聚合 ≥90%、1 条契约测试、4 次 PR 评审记录、评审清单 v1.0）+ Sprint Review

## 1. 分支拆分

| # | 分支 | 内容 | 对应步骤 |
|:--|:--|:--|:--|
| 1 | `feat/answers-votes` | 回答 + 投票 | 3.1 + 3.2（迭代 2） |
| 2 | `feat/accept-comments` | 采纳 + 评论 | 3.3 + 3.4（迭代 3） |
| 3 | `feat/tags` | 标签目录 | 3.5（迭代 4 前半） |
| 4 | `feat/reputation` | 声誉 + Celery（单独细案） | 3.6（迭代 4 后半） |
| 5 | 阶段收尾 | 测试冲刺 + Sprint Review | 3.7 + 3.8 |

## 2. 分支 1 `feat/answers-votes` 六步法细案

### 步骤 1 — domain

- 新建 `app/contexts/qa/domain/answer.py`：`AnswerPosted` 事件 + `Answer` 聚合根（`post()` 工厂、`is_accepted`、`votes_count` 读时聚合字段）。不变式：正文非空（Body 值对象校验）；已采纳禁删（3.3 落 `accept()` 后由删除路径强制，本迭代无删除用例）。注："问题已关闭禁回答"随 Q08 在迭代 5 落地（aggregates.md 定稿），本迭代不实现、不留桩
- 新建 `app/contexts/qa/domain/vote.py`：`VoteTarget` 枚举 + `VoteDirection` 枚举（up/down，1.3 L144"投赞成或反对票"）+ `Vote` 冻结值对象（`cast()` 工厂含 direction）。一人一票为集合级不变式 → 仓储事前检查 + 复合唯一索引兜底（同一用户对同一目标无论方向仅一条记录）
- 扩展 `domain/repository.py`：`AnswerRepository`（add/get_by_id/list_by_question 按 D2 排序）、`VoteRepository`（find_by_user_target/add）
- 领域事件（v2 修订）：`VoteCast` 由 `VoteOnUseCase` 投票成功即发，分支 4 只加消费方。归属说明：aggregates.md L43/L56 将 `VoteCast` 定稿为聚合事件，但本计划将 Vote 建模为独立值对象 + 独立仓储（不载入 Question/Answer 聚合，一人一票靠复合唯一索引兜底），事件无法由聚合发出，故由应用层用例代发，沿用"无订阅者照发"模式——此建模偏差已自裁接受（2026-09-22）：一人一票靠库级复合唯一索引兜底，比聚合内维护投票集合更可靠，事件由用例代发是其自然结果
- 验收：纯 Python、无 FastAPI/SQLAlchemy import

### 步骤 2 — application

- 扩展 `application/commands.py`：`PostAnswer` / `VoteOn` 命令
- 新建 `answer_use_case.py` `PostAnswerUseCase`：问题不存在→404 语义；Body 校验失败→422；`Answer.post()` + `answer_repo.add`
- 新建 `vote_use_case.py` `VoteOnUseCase`：按 target_type 定位 Question/Answer（不存在→404）；`find_by_user_target` 已有票→409；`Vote.cast()`（含 direction）+ `add`；成功发 `VoteCast` 事件
- 扩展 `get_question_use_case.py`：详情组装 answers 区（调 `list_by_question`）
- 验收：fake 仓储单元测试可跑

### 步骤 3 — infrastructure

- 扩展 `infrastructure/models.py`：`answers` 表（id/body/question_id/author_id/created_at/updated_at/is_accepted，FK CASCADE + question_id 索引）；`votes` 表（id/user_id/target_type/target_id/direction/created_at，**复合唯一索引 user_id+target_type+target_id**，一人一票不分方向）。questions 表本分支不加列（v2 修订：closed_at 移除）
- 新建仓储实现：`SqlAlchemyAnswerRepository`（list_by_question 排序：is_accepted DESC → votes DESC → created_at ASC → id tiebreaker；票数 COUNT 子查询）、`SqlAlchemyVoteRepository`（IntegrityError→重复票信号）
- Alembic：`--autogenerate` → 人工审核脚本 → upgrade（纪律 2.7）
- 验收：迁移可 up/down；mypy --strict 过

### 步骤 4 — interfaces/api

- `routes.py`：`POST /api/v1/questions/{qid}/answers`（登录，201 + AnswerResponse）；`POST /api/v1/questions/{qid}/vote`、`POST /api/v1/answers/{aid}/vote`（登录，请求体带 direction，204；重复票 409）
- `schemas.py`：`PostAnswerRequest` / `VoteRequest`（direction） / `AnswerResponse`（id/body/author_id/created_at/votes/is_accepted）
- `GET /api/v1/questions` 增加排序参数（v2 修订：1.3 L162-164"按投票排序"属迭代 2 US-Q02）——默认 latest 不变，可选 votes（净票数，裁定 #1）
- 详情响应 answers 区实装（不再恒空）
- 重导出 `openapi.json` + `--check`（CI 防漂移）
- 验收：契约变更入库

### 步骤 5 — 测试

- 单元（fake 仓储）：Answer 不变式、Vote 枚举校验、D2 排序纯逻辑
- 集成（`@pytest.mark.integration`）：答题 201 / 未登录 401 / 重复票 409 / 复合唯一并发兜底 / 详情 answers 排序（采纳置顶 + 票数）/ 投票 up-down 值合法性与净票口径 / 列表 votes 排序
- 门禁四件套：pytest / ruff / mypy / coverage

### 步骤 6 — 暴力测试 + 台账

- 新攻击面表（未登录 / 重复票并发 / 非法 direction 值 / 超长正文 / 注入 / 排序篡改）→ `docs/test/3.1-answers-votes.md` + `docs/PROGRESS.md` 变更记录

## 3. 分支 2–4 细案

### 分支 2 `feat/accept-comments`

- domain：`Answer.accept()`（重复采纳→409）+ `Question.accepted_answer_id`（跨聚合编排：采纳双写两侧）+ `AnswerAccepted` 事件（原稿误写 CommentAccepted，已修正）+ `Comment` **实体**（v2 修订，aggregates.md L17 定稿：题评挂 Question 聚合、答评挂 Answer 聚合，非独立聚合非值对象）+ `CommentCreated` 事件
- application：`AcceptAnswerUseCase`（仅提问者 403 / 回答不属该问题 404 / 幂等）、`CreateCommentUseCase`（正文校验 / 目标存在）。事务边界（v2 修订）：采纳双写 `Answer.is_accepted` + `Question.accepted_answer_id` 在单 Session 事务内完成，任一侧失败整体回滚
- infra：questions 加 `accepted_answer_id` 列 + `comments` 表（target_type + target_id 索引）
- api：`POST /answers/{id}/accept`（204）、`POST /questions/{id}/comments`、`POST /answers/{id}/comments`（201）

### 分支 3 `feat/tags`

- domain：`TagCatalog` 聚合（同名唯一归并，T02 决策）、Question 挂 tags ≤5（Q03）
- infra：`tags` 表 + `question_tags` 关联表
- api：`GET /tags`、`POST /questions` 带 tags、详情/列表含 tags

### 分支 4 `feat/reputation`

- **先出 Celery 单独细案批准再写码（D3）**——worker/重试/幂等/CI 无 services 处置
- domain：`ReputationLedger`（event_id 唯一索引幂等）
- 链路：`VoteCast` / `AnswerAccepted` → Celery 任务 → 记账（v2 修订：`VoteCast` 分支 1 已随投票发出，本分支只加 Celery 消费方，不再"补发"）
- api：`GET /users/{id}/reputation`

### 块 5 测试冲刺 + Sprint Review

- 3.7：覆盖率 70%+（核心聚合 90%+）、1 条契约测试、4 次 PR 评审记录、评审清单 v1.0
- 3.8：演示录屏 + Retro（Start/Stop/Continue）+ ≥1 份新 ADR
- 开工前单独细案送审

## 4. 决策点

| # | 决策 | 内容 |
|:--|:--|:--|
| D1 | 投票写库 | 同步事务内写，立即幂等可见；仅声誉结算走 Celery |
| D2 | 回答排序 | 已采纳恒最前 > 其余按票数 DESC（继承 1.3 定稿） |
| D3 | Celery 引入 | 分支 4 单独细案、不混分支（延续"新组件单独细案"约定） |

## 5. 待审问题裁定结果（2026-09-22 自裁定稿，不再送外审）

> 沿革：原 #1（Vote 方向）核实为既定需求（1.3 L144）直接落 `VoteDirection`；原 #2（close 端点缺位）裁定砍 closed_at 预埋（归迭代 5）。剩余 5 项裁定如下，实现时不再回退重议。

| # | 项 | 裁定 | 依据/说明 |
|:--|:--|:--|:--|
| 1 | 票数口径 | **净票数（up − down）**，展示可为负 | 存在反对票即应计净分，与声誉"赞加反减"一致（SO 惯例）；D2 详情排序与列表 votes 排序均按净票数 |
| 2 | 评论"已关闭禁评"约束 | **随 Q08 在迭代 5 一并落地**，本阶段不预埋 | 与砍 closed_at 同一范围逻辑，不留桩 |
| 3 | 采纳信息展示 | **返回顶层 `accepted_answer_id`**（nullable） | 分支 2 本就落该列，schema 加一字段零成本，前端可直接定位 |
| 4 | 列表 votes 排序深度 | **迭代 2（分支 1）实现**，LEFT JOIN COUNT 聚合 | 场景已定稿归迭代 2（1.3 L162-164，2026-09-19 移入功能域 7），数据量小 |
| 5 | 改票 | **不允许**：对同一目标再次投票一律 409 | 1.3 L152-155 字面即如此；复合唯一索引 (user_id, target_type, target_id) 零改动支撑。**若将来放开改票**：唯一索引保持不含 direction，异向再投语义改为 UPDATE direction 覆盖，同向重复仍 409（v3 修正：v2 原表述"索引含 direction 且 UPDATE 覆盖"自相矛盾——含 direction 则 up/down 可并存，UPDATE 覆盖以不含 direction 为前提） |

## 6. 附：已预写的步骤 1 domain 代码（处置已定：全量回滚重写）

- 新建：`app/contexts/qa/domain/answer.py`、`app/contexts/qa/domain/vote.py`
- 修改：`app/contexts/qa/domain/repository.py`、`app/contexts/qa/domain/question.py`

处置（2026-09-22 定稿）：**全量回滚**——`question.py`/`repository.py` 还原至阶段 2 原状（撤销 closed_at/is_closed/close() 与 Answer/Vote 协议增量），删除 `answer.py`/`vote.py`；分支 1 步骤 1 按本计划 v3 干净重写。理由：v1 残留与 v3 设计（direction 字段、无关闭桩）混改的不一致风险大于重写成本。当前冻结未提交（git 工作区），回滚动作单独批准执行。
