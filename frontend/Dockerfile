FROM node:22-alpine AS builder

WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm run build

FROM nginx:1.27-alpine AS runtime

ENV API_UPSTREAM=http://127.0.0.1:8123 \
    NGINX_ENVSUBST_TEMPLATE_VARS=API_UPSTREAM

COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O - http://127.0.0.1/healthz | grep -q '^ok$'
