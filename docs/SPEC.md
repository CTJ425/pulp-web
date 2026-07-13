# Lab Local Mirror 服務規格書 (SPEC)

> 基於 Pulp 3 的多格式套件鏡像服務,支援 RPM / DEB / Container Image,
> 搭配自建前端網頁供使用者自助建立與同步 Repository。

- 文件版本:v0.1 (Draft)
- 最後更新:2026-07-13
- 相關文件:`TROUBLESHOOTING.md`(排錯)、`VERIFICATION.md`(驗證)

---

## 1. 背景與目標

### 1.1 問題描述

Lab 內多台主機(實體機、VM、CI runner、K8s 節點)各自向外部來源
(CentOS/Rocky mirror、Ubuntu archive、Docker Hub、Quay 等)抓取套件與映像檔,造成:

1. 對外頻寬重複消耗,同一個套件被下載數十次。
2. 受外部服務 rate limit 影響(尤其 Docker Hub 匿名 pull 限制)。
3. 無網段隔離環境(air-gapped / 半隔離 lab)無法直接安裝套件。
4. 套件版本不一致,無法凍結某個時間點的 repo 狀態做重現性測試。

### 1.2 目標

| # | 目標 | 成功指標 |
|---|------|---------|
| G1 | 集中化下載:外部流量僅由 mirror server 產生 | 用戶端主機對外套件流量趨近 0 |
| G2 | 支援 RPM、DEB、Container 三種內容型態 | dnf/yum、apt、docker/podman pull 全部可用 |
| G3 | 使用者自助:透過 Web UI 建立/同步/管理 repo | 不需 SSH 進 mirror server 即可完成日常操作 |
| G4 | 版本凍結:可保留 repo 歷史版本並隨時發佈舊版 | 可將 distribution 指回任一 repository version |
| G5 | 可觀測:同步狀態、任務進度、磁碟用量可視化 | Web UI 呈現 task 狀態與 storage 統計 |

### 1.3 非目標 (Out of Scope)

- 不做套件簽章代管(GPG 簽章仍沿用上游或另行處理)。
- 不做使用者上傳私有套件的完整 workflow(Phase 2 再議)。
- 不做跨站台 mirror replication(單一 lab 站台)。
- PyPI / npm / Maven 等其他格式為 Phase 2 選配。

---

## 2. 系統架構

### 2.1 架構總覽

```
                         ┌────────────────────────────────────┐
   Internet              │           Mirror Server            │
┌───────────┐            │                                    │
│ Docker Hub│◄──────┐    │  ┌──────────┐    ┌──────────────┐  │
│ Quay.io   │       │    │  │ 前端 Web │───►│ Backend API  │  │
│ Ubuntu    │◄──────┼────┼──│ (React)  │    │ (FastAPI,    │  │
│ Rocky/EPEL│       │    │  └──────────┘    │  BFF/Proxy)  │  │
└───────────┘       │    │                  └──────┬───────┘  │
                    │    │                         │ REST     │
                    │    │  ┌──────────────────────▼───────┐  │
                    └────┼──┤        Pulp 3 (pulpcore)     │  │
                         │  │  plugins: rpm / deb /        │  │
                         │  │           container          │  │
                         │  ├──────────┬─────────┬─────────┤  │
                         │  │PostgreSQL│  Redis  │ Storage │  │
                         │  └──────────┴─────────┴─────────┘  │
                         │        ▲ pulp-content (serve)      │
                         └────────┼───────────────────────────┘
                                  │ HTTP(S)
        ┌─────────────┬───────────┴──────────┬───────────────┐
        │ dnf/yum 主機 │      apt 主機        │ docker/podman │
        └─────────────┴──────────────────────┴───────────────┘
```

### 2.2 元件清單

| 元件 | 技術選型 | 角色 |
|------|---------|------|
| pulpcore | Pulp 3 (>= 3.49 LTS,以部署當下最新 stable 為準) | 核心:repository、task、storage 管理 |
| pulp_rpm | Pulp plugin | RPM repo 同步與發佈(yum/dnf metadata) |
| pulp_deb | Pulp plugin | APT repo 同步與發佈 |
| pulp_container | Pulp plugin | OCI/Docker registry 同步與發佈 |
| PostgreSQL | 13+ | Pulp 後端資料庫 |
| Redis | 6+ | Task queue / cache |
| pulp-content | pulpcore 內建 | 對用戶端提供實際下載內容 |
| pulp-api | pulpcore 內建 | REST API (`/pulp/api/v3/`) |
| pulp-worker | pulpcore 內建 | 執行同步/發佈等非同步任務(建議 >= 2 個) |
| Backend (BFF) | Python FastAPI | 前端專用 API:封裝 Pulp API、處理認證、簡化操作流程 |
| Frontend | React + TypeScript (Vite) | 使用者自助操作介面 |
| Reverse Proxy | Nginx | TLS 終結、路由 `/`(前端)、`/api`(BFF)、`/pulp`(Pulp)、registry v2 端點 |

### 2.3 部署方式(全容器化,最終落地 Kubernetes)

**部署原則:所有元件一律容器化,不做裸機安裝。** 分兩階段:

| 階段 | 環境 | 用途 | 生命週期 |
|------|------|------|---------|
| Stage 1 | Docker Compose(單機) | POC、開發、功能驗證 | 驗證通過後轉入 Stage 2,可保留作 staging |
| Stage 2 | **Kubernetes + pulp-operator(正式環境)** | Lab 正式服務 | 長期營運目標 |

兩階段共用同一套自建 image(BFF、Frontend),確保驗證結果可平移。
詳細操作步驟見 `DEPLOYMENT.md`,部署後驗證見 `VERIFICATION.md` §1。

#### 2.3.1 Stage 1 — Docker Compose(POC / Staging)

採 Pulp 官方 `pulp/pulp` single-container image + 周邊服務。
檔案佈局跟隨 repo 目錄結構(見 `CLAUDE.md`):

```
deploy/compose/
├── compose.yml            # pulp + postgres + redis + bff + frontend + nginx
├── settings/
│   └── settings.py        # Pulp 設定 (DATABASES / ALLOWED_CONTENT_CHECKSUMS 等)
└── nginx/
    └── mirror.conf
bff/                       # FastAPI 專案 (含 Dockerfile;compose 以 ../../bff 為 build context)
frontend/                  # React 專案 (含 Dockerfile, multi-stage build → nginx serve)
```

#### 2.3.2 Stage 2 — Kubernetes(正式環境)

**Pulp 本體使用官方 [pulp-operator](https://github.com/pulp/pulp-operator) 部署與管理**,
自建元件(BFF / Frontend)以標準 Deployment 部署,全部宣告式 YAML 納入 Git(GitOps-ready)。

拓撲與資源對應:

| K8s 資源 | 內容 | 說明 |
|----------|------|------|
| Namespace | `pulp-mirror` | 全部元件集中一個 namespace |
| CRD `Pulp` | pulp-operator 的自訂資源 | 一份 YAML 宣告 api/content/worker replicas、storage、DB |
| Deployment | `pulp-api` ×2、`pulp-content` ×2、`pulp-worker` ×2+ | 由 operator 產生,replicas 於 CR 中宣告 |
| Deployment | `bff` ×2、`frontend` ×2 | 自建 image,自行維護 manifest / Helm chart |
| StatefulSet | `postgres`(operator 內建或外部 DB) | 正式環境建議獨立 PostgreSQL(CloudNativePG 或既有 DBaaS) |
| Deployment | `redis` | operator 內建即可 |
| PVC | `pulp-file-storage`(**RWX**) | pulp-api / content / worker 共掛;無 RWX StorageClass 時改用 S3/MinIO(見下) |
| Ingress | `mirror.lab.local` | 路由 `/` → frontend、`/api` → bff、`/pulp` 與 `/v2` → pulp(content/api) |
| Secret | pulp admin 密碼、DB 密碼、上游 registry 憑證、TLS 憑證 | 建議搭配 external-secrets 或 sealed-secrets |
| CronJob | `orphan-cleanup`、`repo-sync-*` | 排程同步可用 K8s CronJob 呼叫 BFF API 取代內建 scheduler |

**儲存決策(關鍵)**:

| 選項 | 條件 | 備註 |
|------|------|------|
| RWX PVC(NFS / CephFS / Longhorn RWX) | Lab 已有對應 StorageClass | 最貼近單機行為,遷移簡單 |
| S3 相容物件儲存(MinIO / Ceph RGW) | 無 RWX 或想水平擴 content | Pulp 原生支援 `storages.backends.s3boto3`;pulp CR 直接宣告 `object_storage_s3_secret` |

**Ingress 特殊需求**(registry v2 大檔上傳/下載):
- `nginx.ingress.kubernetes.io/proxy-body-size: "0"`
- `proxy-request-buffering: "off"`、`proxy-read-timeout: "900"`
- TLS 由 cert-manager 簽發(內部 CA ClusterIssuer)

**版本與升級**:pulpcore/plugin 版本鎖定於 Pulp CR 的 image tag;升級流程 = 改 CR → operator 滾動更新 → 跑 VERIFICATION 冒煙。

#### 2.3.3 自建 image 規範

| Image | Base | 要求 |
|-------|------|------|
| `lab/mirror-bff` | `python:3.12-slim` | multi-stage、non-root、healthcheck `/api/v1/health`、設定全走環境變數 |
| `lab/mirror-frontend` | build: `node:22` → run: `nginxinc/nginx-unprivileged` | 靜態檔輸出、API base URL 以 runtime env 注入 |

自建 image 推入 lab 內部 registry(可以就是本 mirror 的 container distribution,但 bootstrap 階段需外部 registry 或先 side-load)。

### 2.4 硬體/容量建議

| 資源 | 建議最低值 | 說明 |
|------|-----------|------|
| CPU | 8 vCPU | 同步 + metadata 產生為 CPU 密集 |
| RAM | 16 GB | worker 數量多時需增加 |
| Storage | 2 TB(可擴充,建議 LVM/ZFS) | 一份完整 Rocky 9 BaseOS+AppStream 約 90 GB;Ubuntu main+universe 約 300 GB+;container 視使用量 |
| 網路 | 對外 >= 100 Mbps;對內 1 Gbps+ | 初次同步時間受對外頻寬決定 |

> **重點**:啟用 `on_demand` 下載策略時,實際磁碟用量僅為「被用戶端要求過的內容」,可大幅節省空間(見 3.4)。

---

## 3. 功能規格

### 3.1 內容型態支援矩陣

| 功能 | RPM | DEB | Container |
|------|-----|-----|-----------|
| 從上游同步 (mirror) | ✅ remote + sync | ✅ remote + sync | ✅ remote + sync |
| Pull-through cache(用到才抓) | ✅ policy=on_demand | ✅ policy=on_demand | ✅ pull-through cache distribution |
| 版本凍結 / 回滾 | ✅ repository versions | ✅ | ✅ |
| 過濾同步(只抓部分內容) | ✅ 依套件名/架構 | ✅ 依 component/architecture | ✅ 依 tag(include/exclude_tags) |
| 用戶端協定 | HTTP(S) yum repo | HTTP(S) apt repo | Docker Registry v2 API |

### 3.2 使用者故事 (User Stories)

| ID | 角色 | 需求 |
|----|------|------|
| US-01 | Lab 使用者 | 我要在 Web UI 上看到目前有哪些 repo 可用,以及對應的用戶端設定方式(可一鍵複製 `.repo` / `sources.list` / registry 設定) |
| US-02 | Repo 管理者 | 我要新增一個上游來源(URL、GPG、架構、tag filter),並手動或排程觸發同步 |
| US-03 | Repo 管理者 | 我要看到每次同步任務的進度、結果與錯誤訊息 |
| US-04 | Repo 管理者 | 我要把某個 distribution 固定在某一個 repository version(凍結),或切回 latest |
| US-05 | 管理員 | 我要看到磁碟使用量、各 repo 佔用空間,並能執行 orphan cleanup |
| US-06 | 管理員 | 我要管理使用者帳號與角色(唯讀 / repo 管理者 / 系統管理員) |

### 3.3 Web UI 頁面規格

| 頁面 | 主要內容 | 對應 Pulp API |
|------|---------|--------------|
| Dashboard | repo 總數、最近同步狀態、磁碟用量、失敗任務數 | `/pulp/api/v3/status/`, tasks, artifacts 統計 |
| Repositories 列表 | 三種型態 repo 清單、最新版本、上次同步時間、`Sync now` 按鈕 | `repositories/{rpm,deb,container}/` |
| Repository 詳情 | 版本歷史、內容摘要(套件數/tag 數)、distribution 綁定、凍結操作 | `repository_versions/`, `distributions/` |
| 新增 Repo 精靈 | Step1 選型態 → Step2 上游 URL/認證/filter → Step3 同步策略(immediate/on_demand)→ Step4 distribution base_path | `remotes/`, `repositories/`, `distributions/` |
| Tasks | 任務列表(running/completed/failed)、進度條、error traceback | `tasks/` |
| Client Setup | 依 repo 自動產生用戶端設定片段 | (BFF 端組字串) |
| Admin | 使用者/角色、排程(cron)、orphan cleanup、備份提示 | `users/`, `roles/`, BFF scheduler |

### 3.4 同步策略(重要設計決策)

| 策略 | 行為 | 適用場景 |
|------|------|---------|
| `immediate` | 同步時完整下載所有內容 | 需要 air-gapped 完整鏡像、或要做離線媒體 |
| `on_demand` | 只抓 metadata,artifact 在用戶端第一次要求時才向上游抓並快取 | **預設建議**。大幅節省磁碟與初次同步時間 |
| `streamed` | 同 on_demand 但不落地快取 | 一般不建議(失去 mirror 意義) |

Container 額外支援 **pull-through cache**:建立一個特殊 distribution 指向上游 registry,
用戶端 pull 任何 image 都會自動快取,無需事先逐一建立 repo。適合作為 Docker Hub 的透明快取。

### 3.5 排程同步

- BFF 內建 scheduler(APScheduler)或系統 cron 呼叫 BFF API。
- 每個 repo 可設定 cron expression(如 `0 2 * * *` 每日 02:00)。
- 排程觸發時 BFF 呼叫 Pulp sync API,並記錄 task href 供 UI 查詢。
- 同一 repo 若上一次 sync 尚在執行,跳過本次並記 warning。

### 3.6 認證與授權

| 層 | 機制 |
|----|------|
| Web UI / BFF | 帳密登入(可選 LDAP/OIDC 整合),JWT session |
| BFF → Pulp API | 服務帳號 (basic auth over TLS),使用者不直接接觸 Pulp 帳密 |
| 用戶端拉取內容 | 預設匿名可讀(lab 內網);container push(若開放)需帳號 |
| 角色 | `viewer`(唯讀)/ `operator`(可 sync、凍結)/ `admin`(全部) |

### 3.7 API 規格(BFF,節錄)

```
GET    /api/v1/repos?type={rpm|deb|container}      # 列表
POST   /api/v1/repos                               # 建立 (含 remote+repo+distribution)
POST   /api/v1/repos/{id}/sync                     # 觸發同步 → 回傳 task id
GET    /api/v1/repos/{id}/versions                 # 版本歷史
POST   /api/v1/repos/{id}/pin                      # 凍結 distribution 至指定 version
GET    /api/v1/tasks?state={running|failed|...}    # 任務查詢
GET    /api/v1/repos/{id}/client-config            # 產生用戶端設定文字
POST   /api/v1/admin/orphan-cleanup                # 觸發 orphan cleanup
GET    /api/v1/system/storage                      # 磁碟統計
```

BFF 對 Pulp 的所有非同步操作(sync、publish、cleanup)一律回傳 202 + task 資訊,前端輪詢 task 狀態。

`{id}` 定義:BFF 以 **repo 名稱**作為識別(建立時強制全域唯一,跨 rpm/deb/container 不得重名),
URL 與排程設定(如 K8s CronJob)直接使用名稱,避免暴露 Pulp href/UUID。

---

## 4. 用戶端接入規格

### 4.1 RPM (dnf/yum)

`/etc/yum.repos.d/lab-mirror-rocky9-baseos.repo`:

```ini
[lab-rocky9-baseos]
name=Lab Mirror - Rocky 9 BaseOS
baseurl=https://mirror.lab.local/pulp/content/rocky9-baseos/
enabled=1
gpgcheck=1
gpgkey=https://mirror.lab.local/keys/RPM-GPG-KEY-Rocky-9
```

### 4.2 DEB (apt)

`/etc/apt/sources.list.d/lab-mirror.list`:

```
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://mirror.lab.local/pulp/content/ubuntu-noble/ noble main
```

> sources.list 的 component 必須落在 remote 同步範圍內(參考值:main;
> 若 remote 亦同步 universe 才可加上),否則 apt 會報
> `doesn't have component` (TROUBLESHOOTING §4.4)。

### 4.3 Container (docker/podman)

方式 A — registry mirror(建議,對使用者透明):

`/etc/docker/daemon.json`:
```json
{ "registry-mirrors": ["https://mirror.lab.local"] }
```

podman `/etc/containers/registries.conf`:
```toml
[[registry]]
prefix = "docker.io"
location = "docker.io"
[[registry.mirror]]
location = "mirror.lab.local"
```

方式 B — 直接指名:
```
docker pull mirror.lab.local/library/nginx:1.27
```

> Registry v2 需求:Nginx 需正確轉發 `/v2/` 到 pulp-content,並設定
> `client_max_body_size 0`、關閉 buffering(見 TROUBLESHOOTING §6)。

---

## 5. 非功能需求

| 項目 | 規格 |
|------|------|
| TLS | 內部 CA 簽發,所有用戶端匯入 CA;或使用 lab 既有 PKI |
| 備份 | PostgreSQL 每日 dump;`/var/lib/pulp` storage 依快照策略(ZFS snapshot 或 rsync) |
| 監控 | Pulp `/pulp/api/v3/status/` 健康檢查;Prometheus node/postgres exporter;磁碟用量告警 80% |
| 日誌 | 容器日誌集中(journald / Loki 皆可);task 失敗記錄保留 90 天 |
| 磁碟保護 | 定期 orphan cleanup;repo `retain_repo_versions` 預設 5 |
| 可用性 | 單機即可(lab 等級);計畫性維護窗口通知 |

---

## 6. 里程碑

| Phase | 內容 | 驗收 |
|-------|------|------|
| P0 | **Docker Compose 部署** Pulp + 手動 CLI 建立 rpm/deb/container 各一組 repo | VERIFICATION.md §1A、§2–4 全過 |
| P1 | BFF API + 前端(Dashboard、Repo 列表、Sync、Tasks),元件容器化 image 定版 | US-01~03 |
| P2 | 版本凍結、排程、Client Setup 產生器、RBAC | US-04~06 |
| P3 | **遷移至 Kubernetes**:pulp-operator 部署、BFF/Frontend manifests、Ingress、資料遷移 | VERIFICATION.md §1B 全過 + §2–4 於 K8s 環境重跑 |
| P4 | 監控告警(Prometheus/ServiceMonitor)、備份演練、容量治理、CronJob 排程化 | 演練報告 |

---

## 7. 風險與對策

| 風險 | 對策 |
|------|------|
| Docker Hub rate limit 導致同步失敗 | 使用付費帳號憑證設定於 remote;pull-through cache 減少重複請求 |
| 磁碟爆滿 | on_demand 策略 + retain_repo_versions + 週期 orphan cleanup + 用量告警 |
| 上游 metadata 格式變動 / plugin bug | 固定 Pulp 版本、升級前於 staging 驗證;訂閱 pulp release note |
| 單點故障 | K8s 上 api/content/worker 皆 >= 2 replicas;備份可於 4 小時內重建 |
| SHA-1 簽章的舊 repo 無法同步 | `ALLOWED_CONTENT_CHECKSUMS` 設定調整(見 TROUBLESHOOTING §3.4) |
| K8s 無 RWX StorageClass | 改用 S3/MinIO 物件儲存後端(見 2.3.2 儲存決策) |
| Compose → K8s 資料遷移失敗 | 遷移採「DB dump/restore + storage rsync(或直接改接 S3)」並先於 staging 演練;保留 Compose 環境直到 K8s 驗收通過 |
| Bootstrap 循環依賴(mirror 自己也是 registry) | 自建 image 先放外部/暫時 registry;K8s 節點的 image pull 不可依賴尚未就緒的 mirror |
