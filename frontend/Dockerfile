# Admin panel image: build the Vite bundle with Node, serve dist/ with nginx.
# nginx.conf adds the SPA fallback and proxies /v1/ to the `api` service of the compose file.
# It also serves the embeddable widget at /widget/v1/knobridge-chat.js (docs/specs/widget.md),
# built from the `widget` build context (`additional_contexts` in docker-compose.yml).

FROM node:24-alpine AS build
# pnpm comes from corepack, at the exact version pinned in package.json (packageManager).
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /app

# Dependencies first, so source changes do not invalidate this layer.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# The widget is its own pnpm package (widget/), with its own lockfile and pnpm version.
FROM node:24-alpine AS widget-build
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /widget
COPY --from=widget package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY --from=widget . .
# One IIFE file; the build fails above the 60 KiB gzip budget.
RUN pnpm build

FROM nginx:alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=widget-build /widget/dist/knobridge-chat.js /usr/share/nginx/html/widget/v1/knobridge-chat.js
EXPOSE 80
