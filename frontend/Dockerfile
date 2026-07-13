# lab/mirror-frontend(SPEC §2.3.3):node build → nginx-unprivileged 靜態服務
# API base URL 由 runtime 環境變數 API_BASE_URL 注入(40-runtime-config.sh)
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27
# healthcheck 需要 curl(nginx 映像未內建)
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*
USER nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf
# entrypoint script 以 nginx 使用者執行,需要能寫 config.js
COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html
COPY --chmod=755 docker/40-runtime-config.sh /docker-entrypoint.d/40-runtime-config.sh
ENV API_BASE_URL=/api
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD ["curl", "-sf", "http://localhost:8080/"]
