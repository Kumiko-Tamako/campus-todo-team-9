# 阶段 3 演示脚本（Sprint Review · 步骤 3.8 交付物①）

> 用途：端到端演示注册→提问→回答→投票→采纳→评论→声誉结算全链路。
> 主线走 Swagger UI（`/docs`），curl 命令在附录（无 GUI 环境或录屏备用）。
> **录屏由执行人（用户）完成**，本脚本含录屏检查单。

## 〇、环境准备（演示前 10 分钟）

| # | 检查 | 命令 / 判据 |
|:--|:--|:--|
| 1 | 数据服务 | `docker compose up -d` → `campusoverflow-db-1`、`redis-1` 双 healthy |
| 2 | 库结构最新 | `.venv\Scripts\python.exe -m alembic upgrade head` → 无报错（已最新则空操作） |
| 3 | 干净起点 | 建议新库或先清业务表（演示数据量小，混着旧数据不影响，但截图更干净） |
| 4 | API 服务 | `.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001`（8000 被 Hyper-V 保留区间占用，历史台账记录） |
| 5 | **Celery worker（必开！）** | 新终端：`.venv\Scripts\python.exe -m celery -A app.contexts.reputation.infrastructure.celery_app worker --pool=solo -l info`（Windows 必须 `--pool=solo`，ADR-004；**不开 worker 声誉永远不落账**，演示第 9 步会空手） |
| 6 | 就绪确认 | 浏览器 `http://127.0.0.1:8001/docs` 能打开；worker 终端出现 `celery@… ready` |

**失败回退**：任一步失败 → 关掉 worker/uvicorn 终端重跑 1–6；仍失败 → 切 curl 附录
逐条排查（多数是端口占用或 worker 没起）；演示现场不可修复 → 用预置数据（见下）
从第 7 步续演。

**预置数据**：演示前 1 小时先完整跑一遍脚本 1–9 并保留库，现场从第 10 步
（查询已有声誉）开始即可；或录一段备用视频（检查单允许）。

## 一、演示走查（Swagger UI 主线，约 8–10 分钟）

| 步 | 操作（Try it out） | 预期 | 讲解点 |
|:--|:--|:--|:--|
| 1 | `POST /api/v1/auth/register` 用户 A（student，学号自定） | 201 | DDD identity 上下文；bcrypt 哈希不落明文 |
| 2 | 同端点注册用户 B（student） | 201 | 双用户为后续"他人采纳 403"铺垫 |
| 3 | `POST /api/v1/auth/login` A → 复制 `access_token` → Authorize 按钮粘贴 | 200 / Authorize 绿锁 | JWT Access 15min；Refresh 7d 存 Redis 可吊销 |
| 4 | `POST /api/v1/questions` A 提问，带 tags（如 `["数据库","索引"]`） | 201，记下 `question_id` | Tag 值对象同名归并；标签目录 `GET /tags` 可顺带点开 |
| 5 | 切 B 登录 Authorize → `POST /api/v1/questions/{qid}/answers` B 回答 | 201，记下 `answer_id` | 答题者不能是自己题的回答方限制不存在——B 可答 A 的题 |
| 6 | B 对**自己的回答**投赞成 | **200/204 但声誉不加分**（自投不计分，可只口述） | 反刷分规则 |
| 7 | 切回 A → `POST /api/v1/questions/{qid}/answers/{aid}/vote` 赞成 | 204 | 净票数口径 up−down；复合唯一索引一票 |
| 8 | A → `POST /api/v1/answers/{aid}/accept` | **204** | 应用层跨聚合编排 + 部分唯一索引"一题一采纳"库级兜底 |
| 9 | A → `POST /api/v1/questions/{qid}/comments` 评论；B → `POST /api/v1/answers/{aid}/comments` | 201 | Comment 实体多态 target |
| 10 | 切 B 登录 → `GET /api/v1/users/{B_id}/reputation` | total = **+25**（答赞 +10 + 采纳 +15） | **声誉异步结算：等待 ~0.5–2s**（实测 avg 0.41s/max 1.33s），第一次查可能是 0，点两次 Try it out |
| 11 | `GET /api/v1/users/{A_id}/reputation`（A 题主被赞） | total = **+5**（题赞 +5） | 记分矩阵：答赞+10/答踩−2/题赞+5/题踩−2/采纳+15、自投不计分 |

> 注①：数字按 3.6 常量表计算；演示前用预置数据核对一遍实际返回，现场照读。

### 反例镜头（各 15 秒，证明防线在位）

| 步 | 操作 | 预期 | 讲解点 |
|:--|:--|:--|:--|
| 12 | 取消 Authorize（登出态）→ `GET /api/v1/users/{id}/reputation` | **401** | 未认证拒绝 |
| 13 | A 登录 → 查 **B** 的声誉 | **403** | 裁定 4：仅本人可查 |
| 14 | B 尝试采纳自己的回答（`POST /answers/{aid}/accept`） | **403** | NotQuestionAuthor：只有题主能采纳 |

### 收尾

| 步 | 操作 | 讲解点 |
|:--|:--|:--|
| 15 | worker 终端展示 `reputation.apply_vote_delta` / `apply_accept_bonus` 任务日志 | 至少一次投递 + event_id 幂等恰一次记账 |
| 16 | `GET /openapi.json` 或 `/docs` 顶部 | 契约 16 paths/17 ops，CI `--check` 防漂移 + 本地契约测试双保险 |

## 二、录屏检查单（执行人逐项打勾）

- [ ] 分辨率 ≥1080p，终端与浏览器同屏可读（字号调大一档）
- [ ] 时长 8–12 分钟（超时剪掉第 6 步自投口述即可）
- [ ] 第 10 步声誉查询**先等 2 秒再点**，避免拍到 0 引起误解（或保留 0→25 变化作为异步实证，二选一并在讲解中说清）
- [ ] 反例 401/403 三个镜头齐全
- [ ] worker 日志特写镜头（第 15 步）
- [ ] 录屏失败回退：用备用视频 / 截图+讲解

## 附录：curl 版（无 GUI 环境）

```powershell
$H = "http://127.0.0.1:8001"
# 1-2 注册
curl.exe -s -X POST "$H/api/v1/auth/register" -H "Content-Type: application/json" -d '{\"role\":\"student\",\"student_id\":\"2025010001\",\"name\":\"userA\",\"email\":\"a@test.com\",\"password\":\"Passw0rd!\"}'
# 3 登录取 token（python 解析更省事：| python -c "import sys,json;print(json.load(sys.stdin)['access_token'])"）
$tokA = (curl.exe -s -X POST "$H/api/v1/auth/login" -H "Content-Type: application/json" -d '{\"identifier\":\"a@test.com\",\"password\":\"Passw0rd!\"}' | ConvertFrom-Json).access_token
# 4 提问带标签
$q = curl.exe -s -X POST "$H/api/v1/questions" -H "Authorization: Bearer $tokA" -H "Content-Type: application/json" -d '{\"title\":\"索引失效的常见场景？\",\"body\":\"LIKE 前缀通配为什么不走索引\",\"tags\":[\"数据库\",\"索引\"]}' | ConvertFrom-Json
# 5-9 同 Swagger 主线，端点与载荷照抄表格
# 10 声誉（等 2 秒）
curl.exe -s "$H/api/v1/users/<B_id>/reputation" -H "Authorization: Bearer $tokB"
```
