# Frontend Lab Delivery Design

## Scope

This change aligns the existing frontend with the frontend-facing delivery requirements in the CampusOverflow lab PDF (Labs 5-8). It covers engineering quality, tests, container delivery, CI verification, and evidence documentation. It does not add product capabilities that are absent from the current API contract, such as email verification, expanded RBAC, OAuth, deletion, nested comments, search, notifications, or public user profiles.

## Architecture

The existing React 18 + TypeScript + Vite application remains the application boundary. TypeScript strict mode is enabled in the application project. Existing Axios, TanStack Query, React Router, Zustand, and Ant Design usage remains unchanged.

The frontend is packaged by a multi-stage Docker build. A Node builder installs the locked dependencies and creates the Vite production bundle. An Nginx runtime serves the bundle, falls back to `index.html` for SPA routes, and proxies `/api/` to the configured backend service. The Nginx health endpoint is local to the container and does not require authentication.

Compose keeps the existing PostgreSQL and Redis services and adds a frontend service. The frontend service is configurable through an API upstream variable so it can be used with a separately started backend without inventing a backend image or changing the backend runtime contract.

## Test Strategy

Vitest remains the unit and API-client test runner. A coverage command produces a text summary and fails below a pragmatic frontend threshold. Tests focus on API client behavior, auth state, error mapping, and the core question flow helpers already present in the repository.

One contract test loads the checked-in `openapi.json` and asserts that the frontend's required question and auth operations and response fields still exist. This detects accidental frontend/backend contract drift without generating client code.

Playwright provides one browser E2E journey using a deterministic mock API: sign in, open the questions list, open a question detail, and submit a new question. The test is isolated from PostgreSQL, Redis, Celery, and external network services, while the existing API tests continue to cover request paths and payloads.

## CI And Delivery

The frontend CI job runs install, strict typecheck, lint, unit tests with coverage, build, and Playwright E2E. A separate container check builds the frontend image and starts it with a lightweight local probe for `/healthz` and an SPA route. The check must not depend on Docker Compose's database services.

The repository receives a concise frontend deployment and verification guide that records commands, expected checks, environment variables, and the evidence that must be supplied by the team or a real deployment environment. It explicitly marks SonarQube, JaCoCo/Checkstyle, online URLs, review counts, and production monitoring as external/team-owned evidence rather than fabricated local results.

## Error Handling

The existing application error mapping and authentication interceptors are preserved. Test and container failures are surfaced by the relevant command; no test silently falls back to a passing result. Browser tests use stable test IDs or accessible labels and fail when the expected user-visible state is absent.

## Verification

- `pnpm run typecheck` passes with strict TypeScript settings.
- `pnpm run lint`, `pnpm run test:coverage`, and `pnpm run test:e2e` pass locally or report a documented environment prerequisite.
- `pnpm run build` produces the static bundle.
- The frontend Docker image builds and serves `/healthz` plus an SPA route; `/api` is routed to the configured upstream.
- Existing backend tests and OpenAPI drift checks remain unchanged and continue to be the source of truth for backend quality gates.
