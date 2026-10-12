# Admin panel image: build the Vite bundle with Node, serve dist/ with nginx.
# nginx.conf adds the SPA fallback and proxies /v1/ to the `api` service of the compose file.

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

FROM nginx:alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
