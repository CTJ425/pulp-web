# Lab Local Mirror

基於 [Pulp 3](https://pulpproject.org/) 的 lab 套件鏡像服務，支援 **RPM / DEB / Container** 三種格式。lab 內主機從本地鏡像取得套件與映像檔，不需各自連外；使用者透過自建的 Web UI 自助建立、同步、管理 repo，不需 SSH 進主機操作。

主要能力：

- 集中下載：上游（Rocky / Ubuntu / Docker Hub 等）只抓一次，內部共用
- 自助管理：Web UI 建 repo、觸發 sync、查看任務狀態與磁碟用量
- 版本治理：repo version 保留與回滾（`retain_repo_versions`）、orphan cleanup

## 架構

```
                    ┌──────────────────────── nginx (統一入口 :8080) ───────────────────────┐
  使用者瀏覽器 ────▶│  /            → frontend (React + TS, Vite)                           │
  API 用戶端  ────▶│  /api/        → bff (FastAPI, 簡化並代理 Pulp API)                    │
  dnf / apt   ────▶│  /pulp/       → Pulp 3 API 與 content(/pulp/content/<base_path>/)     │
  docker pull ────▶│  /v2/         → Pulp container registry                                │
                    └────────────────────────────────────────────────────────────────────────┘
                                              │
                                   Pulp 3 (pulpcore + rpm/deb/container plugins)
                                              │
                                   PostgreSQL 16  +  Redis 7  +  儲存 volume
```

部署分兩階段（詳見 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)）：

| 階段 | 方式 | 狀態 |
|------|------|------|
| Stage 1 | docker compose（本 repo 的 `deploy/compose/`） | 可用，本 README 的操作皆以此為準 |
| Stage 2 | Kubernetes + pulp-operator | 規劃中，manifests 尚未落地，設計見 DEPLOYMENT.md §2 |

## 目錄結構

```
bff/         FastAPI 專案(Python 3.12, uv 管理依賴)
frontend/    React + TypeScript (Vite)
deploy/
  compose/   Stage 1 compose.yml、nginx 設定、Pulp settings.py
tests/
  unit/      pytest 單元測試(不需環境)
  api/       pytest 打 BFF/Pulp API(需 dev 環境)
  e2e/       Playwright 前端測試(需 dev 環境)
scripts/     gen-env.sh、status.sh、seed-fixtures.sh、smoke.sh 等
fixtures/    迷你上游(tiny-rpm / tiny-deb / tiny-registry),測試與 seed 用
docs/        SPEC / DEPLOYMENT / VERIFICATION / TROUBLESHOOTING / AGENT_DEV
```

## 前置需求

- Docker Engine 24+（含 compose plugin）
- 開發與測試另需：[uv](https://docs.astral.sh/uv/)（Python 3.12，BFF 依賴管理）、Node 22（frontend lint 與 Playwright e2e）

## 部署（dev 環境快速開始）

所有操作一律透過 Makefile：

```bash
make dev     # 一鍵啟動:產生 .env、建 fixtures、compose up --wait、設定 admin 密碼、health check
make seed    # 建立測試 repo(tiny-rpm / tiny-deb / tiny-image)並完成 sync
make status  # 檢查所有服務健康
make smoke   # 冒煙測試(VERIFICATION §8)
```

啟動後開 <http://localhost:8080> 即可使用 Web UI。

- 秘密（DB 密碼、Pulp admin 密碼）由 `scripts/gen-env.sh` 自動亂數產生到 `deploy/compose/.env`，該檔已 git-ignore，**不要提交**。
- 首次啟動 Pulp 需跑 DB migration，`make dev` 會等到 healthy 才返回（最長約 5 分鐘）。
- 收掉環境：`make down`；連資料 volume 一起清：`make down-clean`。

正式環境（`mirror.lab.local`、TLS、`/srv/pulp` 儲存規劃）的完整步驟見 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) §1。

### 服務入口

nginx 統一對外（dev 綁 `127.0.0.1:8080`，port 可由 `.env` 的 `HTTP_PORT` 調整）：

| 路徑 | 服務 |
|------|------|
| `/` | 前端 Web UI |
| `/api/v1/` | BFF API |
| `/pulp/api/v3/` | Pulp 原生 API（如 `/pulp/api/v3/status/`） |
| `/pulp/content/<base_path>/` | 套件內容（dnf / apt 的 baseurl） |
| `/v2/` | Container registry（docker / podman） |

## 操作

### Web UI

- **建立 repo**：選類型（rpm / deb / container）→ 填上游 URL → 選同步政策（`on_demand` 預設，只抓 metadata、用戶端首次下載時才快取；`immediate` 全量下載）→ 設 `base_path`（預設同 repo 名稱）。
- **同步**：repo 頁面觸發 sync，前端輪詢任務狀態。
- **系統概況**：儀表板顯示 repo 數量、執行中/失敗任務、worker 狀態、磁碟用量。

### BFF API

所有路徑以 `/api/v1` 開頭；repo 以**名稱**識別（不外露 Pulp href）；非同步操作一律回 **202 + task id**，用戶端輪詢 `/tasks/{id}`。

| Method / Path | 作用 |
|---------------|------|
| `GET /api/v1/health` | 健康檢查 |
| `GET /api/v1/repos?type={rpm\|deb\|container}` | 列出 repo |
| `POST /api/v1/repos` | 建立 repo（remote + repository + distribution），202 |
| `GET /api/v1/repos/{name}` | 查單一 repo |
| `POST /api/v1/repos/{name}/sync` | 觸發同步，202 |
| `GET /api/v1/repos/{name}/client-config` | 取得該 repo 的用戶端設定片段（純文字） |
| `GET /api/v1/tasks?state=&limit=` | 列任務（state：running / completed / failed …） |
| `GET /api/v1/tasks/{task_id}` | 任務詳情 |
| `GET /api/v1/system/overview` | 系統概況 |
| `POST /api/v1/system/orphan-cleanup` | 清理孤兒內容，202 |

範例——建立並同步一個 RPM repo：

```bash
curl -s -X POST http://localhost:8080/api/v1/repos \
  -H 'Content-Type: application/json' \
  -d '{"name": "rocky9-baseos", "type": "rpm", "url": "https://dl.rockylinux.org/pub/rocky/9/BaseOS/x86_64/os/", "policy": "on_demand"}'
# => 202 {"task": "<task_id>"}

curl -s http://localhost:8080/api/v1/tasks/<task_id>   # 輪詢直到 state=completed
curl -s -X POST http://localhost:8080/api/v1/repos/rocky9-baseos/sync
```

### 用戶端接入

每個 repo 的現成設定片段可直接由 `GET /api/v1/repos/{name}/client-config` 取得（UI 上也有）。完整範例見 [docs/SPEC.md](docs/SPEC.md) §4。

**RPM**（`/etc/yum.repos.d/lab-mirror-<name>.repo`）：

```ini
[lab-rocky9-baseos]
name=Lab Mirror - rocky9-baseos
baseurl=https://mirror.lab.local/pulp/content/rocky9-baseos/
enabled=1
gpgcheck=1
gpgkey=https://mirror.lab.local/keys/RPM-GPG-KEY-Rocky-9
```

**DEB**（`/etc/apt/sources.list.d/lab-mirror.list`）：

```
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://mirror.lab.local/pulp/content/ubuntu-noble/ noble main
```

**Container** —— 透明鏡像（`/etc/docker/daemon.json`）：

```json
{ "registry-mirrors": ["https://mirror.lab.local"] }
```

或直接指定：`docker pull mirror.lab.local/library/nginx:1.27`。

### 維運

- 健康檢查：`make status`
- 抓 log：`docker compose -f deploy/compose/compose.yml logs --since 5m <svc>`（svc：`pulp`、`bff`、`frontend`、`nginx`、`postgres`、`redis`）
- 磁碟治理：repo 預設保留 5 個版本（`retain_repo_versions`）；定期呼叫 `POST /api/v1/system/orphan-cleanup` 釋放不再被引用的內容
- 排錯：先跑 `make status`，再對照 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) 的錯誤對照表；Pulp 相關錯誤先查最近 failed task 的 `error.description`

## 開發與測試

| 指令 | 作用 |
|------|------|
| `make test` | 單元測試（快，無環境需求） |
| `make test-api` | API 整合測試（需 `make dev` 環境） |
| `make e2e` | Playwright 前端測試（需 `make dev` 環境） |
| `make lint` | ruff + oxlint + tsc -b |

改 code 後的最小驗證順序：`make lint` → `make test` → 涉及 API 則 `make test-api` → 涉及 UI 則 `make e2e`。測試用上游一律用 `fixtures/` 的迷你 repo，不要同步真實上游。

## 文件

| 文件 | 內容 |
|------|------|
| [docs/SPEC.md](docs/SPEC.md) | 完整規格：架構、功能矩陣、BFF API、用戶端接入 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Stage 1 compose 正式部署與 Stage 2 K8s 設計 |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | 驗收條件與逐步驗證腳本 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 各層錯誤對照表與診斷 cheat sheet |
| [docs/AGENT_DEV.md](docs/AGENT_DEV.md) | Claude Code / agent 開發整合說明 |
