# CampusOverflow 前端 API 联调设计

## 目标

将 `frontend/` 从演示数据切换为后端真实 API，完成认证和问题的最小端到端流程：注册、登录、当前用户、退出、问题列表、问题详情和发布问题。前端继续使用 React、Ant Design、Zustand、TanStack Query 和 Axios。

## 范围与契约

- API 使用相对路径 `/api`，开发环境由 Vite 代理到可配置的后端地址。
- 认证接口使用 `/api/v1/auth/register`、`/login`、`/refresh`、`/logout` 和 `/me`。
- 注册请求只发送后端契约允许的字段：学生发送 `role`、`email`、`password`、`student_id`；教师发送 `role`、`email`、`password`、`staff_id`。
- 登录请求只发送 `{ identifier, password }`。
- 发布问题只发送 `{ title, body }`，不发送标签或展示层字段。
- 问题列表使用 `id`、`title`、`author_id`、`created_at`；详情另外读取 `body`、`tags`、`answers`。
- 不在本阶段实现投票、浏览量、答案提交、作者姓名查询或刷新令牌持久化以外的用户资料扩展。

## 架构

`src/api/client.ts` 创建 Axios 实例、注入 Bearer access token，并集中处理错误和令牌刷新。`src/api/auth.ts` 与 `src/api/questions.ts` 只负责接口路径和请求/响应类型。Zustand 的认证 store 持久化 `accessToken`、`refreshToken` 和当前用户；页面通过 API 模块调用 store action，不直接拼接请求。

TanStack Query 管理问题列表和详情缓存。发布成功后失效列表查询，并将服务端返回的详情写入对应缓存。路由保护只检查真实 `accessToken`，旧的演示 token 不再视为登录状态。

## 令牌数据流

1. 登录成功得到 `access_token`、`refresh_token` 和过期时间，两个令牌一起保存。
2. 请求拦截器为受保护请求添加 `Authorization: Bearer <access_token>`。
3. 收到 401 时，除刷新请求外，使用当前 refresh token 调用 `/refresh`。
4. 刷新成功后同时替换 access 和 refresh token，并重试原请求一次。
5. 刷新失败或没有 refresh token 时清空会话，页面回到登录入口，避免无限重试。
6. 退出请求失败不阻止本地清理，确保用户可以离开失效会话。

## 错误处理

统一错误函数处理网络错误、401、404、422、400 和 413。422 的 `detail` 可能是数组，提取每项 `msg`；其余情况显示可理解的中文提示。问题详情的 404 显示空态。用户输入仍通过 React 默认文本渲染，不使用 `dangerouslySetInnerHTML`。

## 测试与验证

- API 层测试请求路径、请求体字段和 401 刷新轮换行为。
- 页面测试登录成功/失败、注册字段分流和发布请求体。
- 使用 TypeScript、oxlint、Vite build 和 `git diff --check` 验证。
- 若本地数据库、Redis 或后端服务未启动，只记录为环境阻塞，不用 mock 结果冒充联调成功。

