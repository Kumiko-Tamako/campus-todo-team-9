# 前端部署与验证

本文覆盖 CampusOverflow 前端静态包的本地构建、容器运行和 CI 验证。前端服务只负责 React 静态资源与 `/api/` 反向代理；后端仍由团队的 FastAPI 服务提供。

## 本地质量门禁

在仓库根目录执行：

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run lint
pnpm run test:coverage
pnpm exec playwright install chromium
pnpm run test:e2e
pnpm run build
```

浏览器 E2E 使用 Playwright mock API，不依赖 PostgreSQL、Redis 或外部网络。本机若无法下载 Playwright Chromium，但已安装 Google Chrome，可设置 `PLAYWRIGHT_CHANNEL=chrome` 运行浏览器测试；CI 仍使用其安装的 Chromium。覆盖率门禁针对 API 客户端和注册校验模块执行，其他页面、hooks 和 store 不计入当前覆盖率数字，低于配置阈值时命令失败。

## Docker 运行

直接构建并启动前端：

```powershell
docker build -f frontend/Dockerfile -t campusoverflow-frontend .
docker run --rm -p 8080:80 `
  --add-host host.docker.internal:host-gateway `
  -e API_UPSTREAM=http://host.docker.internal:8123 `
  campusoverflow-frontend
```

验证静态服务和 SPA 回退：

```powershell
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/questions
```

第一个请求应返回 `ok`，第二个请求应返回包含前端根节点的 `index.html`。`API_UPSTREAM` 必须指向实际可访问的后端地址，不能把它写成浏览器无法访问的容器内部地址。

Compose 会保留现有 PostgreSQL、Redis 服务并额外启动前端：

```powershell
$env:API_UPSTREAM = 'http://host.docker.internal:8123'
docker compose up --build frontend
```

前端暴露在 `http://127.0.0.1:8080`。Compose 的健康检查只检查 `/healthz`，不会因为后端尚未启动而误报静态服务故障。

## CI 检查

GitHub Actions 的前端作业依次执行严格 TypeScript、Oxlint、Vitest 覆盖率、Playwright Chromium E2E 和生产构建；独立容器作业构建镜像并检查 `/healthz` 与 `/questions` 的 SPA 回退。

以下内容必须使用真实团队或部署平台证据补充，不能由本地前端提交伪造：线上访问地址、每位成员的代码评审次数、SonarQube/JaCoCo/Checkstyle 报告、生产监控结果，以及依赖真实后端的联调截图。
