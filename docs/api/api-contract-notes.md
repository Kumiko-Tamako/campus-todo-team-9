# CampusOverflow API 契约说明（给前端）

> 配套文件：仓库根 [`openapi.json`](../../openapi.json)（由 `scripts/export_openapi.py` 生成，OpenAPI 3.1）。
> 本文写的是 **schema 表达不了的约定与全局行为**，前端必读。

## 一、生成与防漂移（重要）

- `openapi.json` 由 `python scripts/export_openapi.py` 生成，**任何 API 变更后必须重跑**；
- CI 门禁会执行 `--check` 比对：代码改了契约没重新导出 → **CI 红**；
- 依赖升级（FastAPI/Pydantic）也可能改变 schema 结构触发门禁——这是特性（提醒同步），重跑导出即可；
- `.env` 中**不要覆盖 `app_name`**——`openapi().info.title` 取自它，覆盖后契约文件与 CI 门禁冲突。

## 二、两条接口约定

1. **`extra=forbid`**：所有请求体 schema 禁止多余字段——**多塞任何字段直接 422**。前端请求体严格按 schema 字段发送。
2. **XSS 由前端渲染时转义**：后端对文本**原样存储、原样回显**（含 `<script>`、emoji 等）。所有用户输入内容在 HTML 渲染时必须转义（R-15 统一口径）。

## 三、错误形态速查

| 状态码 | `detail` 形态 | 来源 | 前端处理 |
|:--|:--|:--|:--|
| 422 | **数组** `[{type, loc, msg}]`（不回显 input） | Pydantic 校验（含 extra=forbid、tags 类型/结构/原始数量 >20） | 逐项展示 msg。⚠️ schema 声明的 `input`/`ctx` 是 FastAPI 内置 ValidationError 模型残留，**实际响应永不含这两个键**，请以 type/loc/msg 为准 |
| 422 | **字符串**（中文业务语义，如"至多 5 个标签…""标签含不支持的字符…"） | 领域值对象校验（Title/Body/Tag 与标签去重后 ≤5 上限） | 直接展示该句。**tags 两种 422 形态都要处理**：类型/结构错=数组形，语义违规=字符串形 |
| 401 | 字符串（如"令牌无效或已过期"） | Bearer 依赖层 | 跳登录页 |
| 400 | 字符串"请求数据无法被数据库接受…" | 数据库兜底 | 提示检查输入 |
| 413 | 字符串"request body too large" | 1 MiB body 上限中间件 | 提示内容过大 |
| 404 | 字符串（如"问题不存在"） | 业务语义 | 展示空态 |
| 405 | 标准 Method Not Allowed | 方法面 | —（请求方式写错才会遇到） |
| 503 | 字符串"服务暂时不可用，请稍后重试" | 数据库不可达/连接超时/池排队超时（容量工程异常分层） | **可重试**（指数退避），勿当业务错误 |

**⚠️ 全局错误码不在 schema 内**：`openapi.json` 各路由 `responses` 只声明了 200/201/204/422；上表中的 401/400/413/405/503 来自中间件与依赖层，**生成类型时看不见，但真实存在，前端必须处理**。

## 四、分页契约（`GET /api/v1/questions`）

- 请求：`page ≥ 1`（默认 1）、`page_size` 1~100（默认 20）
- 响应：`{items, total, page, page_size, total_pages}`；**空库 `total_pages = 0`**
- 排序：`created_at` 新→旧（同刻按 id 定序，跨页零重复零漏项）
- 超总页 → **200 空列表**（非 404）

## 四点五、声誉查询口径（`GET /api/v1/users/{user_id}/reputation`）

- **仅本人**（v3.1 裁定 4）：他人查询 → **403**（author_id 在问题/回答已公开，无存在性可泄露）；未登录 401
- **最终一致**：投票/采纳后声誉流水经 Celery **异步**落账（实测结算延迟亚秒~1.3s）——前端**勿假设 204 后同步可查**，展示前轮询或容忍短暂滞后
- `entries` 不分页（流水量小）；`total` 可为负（踩分计入）；空账 `total=0` + 空列表
- 分值口径唯一出处：后端 `reputation/domain/ledger.py` 常量（答赞 +10 / 答踩 −2 / 题赞 +5 / 题踩 −2 / 采纳 +15，自投不计分）

## 五、开发期调试入口

后端跑起来后直接开 **Swagger UI**：`http://localhost:<port>/docs`——交互式调试每个端点，与 `openapi.json` 同源生成。

**HEAD 请求注意**：当前框架对 GET 路由不自动支持 HEAD（连 `/health` 的 HEAD 都 405），探活/预检请统一用 GET。

## 六、前端消费指引

```bash
pnpm add -D openapi-typescript
pnpm add openapi-fetch
npx openapi-typescript ./openapi.json -o src/api/schema.d.ts
```

- 用 `openapi-fetch` 配合生成的 `schema.d.ts` 获得全链路类型；
- **不要用 `openapi-typescript-codegen`**（已停止维护）；
- 令牌格式：`Authorization: Bearer <access_token>`（登录/刷新响应中的 `access_token`，有效期 `expires_in` 秒）。
