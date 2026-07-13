# Lab Local Mirror 部署手冊 (DEPLOYMENT)

對應 `SPEC.md` §2.3 的兩階段部署:
- **Stage 1:Docker Compose**(POC / Staging)
- **Stage 2:Kubernetes + pulp-operator**(正式環境)

每個階段完成後,依 `VERIFICATION.md` §1A / §1B 驗收。

> 版本注意:pulp-operator CRD 欄位與 pulp image tag 隨版本演進,以下 YAML 為結構示意,
> 實作時請對照部署當下的官方文件與 `kubectl explain pulp.spec`。

---

## 1. Stage 1 — Docker Compose 部署

### 1.1 前置條件

- 一台 VM/實體機:8 vCPU / 16 GB RAM / 2 TB(掛載於 `/srv/pulp`)
- Docker Engine 24+ 與 docker compose plugin(或 podman-compose)
- DNS:`mirror.lab.local` 指向本機;內部 CA 簽發之 TLS 憑證
- 對外可達上游來源(或已設定 HTTP proxy)

### 1.2 目錄與設定

```bash
sudo mkdir -p /srv/pulp/{storage,pgsql,settings,certs,keys}
# 700:700 是「uid:gid」數字(pulp 容器內 pulp 使用者的 uid/gid),不是權限模式
sudo chown -R 700:700 /srv/pulp/storage
```

`/srv/pulp/keys/` 放各發行版 GPG 公鑰(如 `RPM-GPG-KEY-Rocky-9`),由 nginx 以 `/keys/` 靜態提供(見 1.4),對應 SPEC §4.1 的 `gpgkey` URL。

`/srv/pulp/settings/settings.py`:
```python
import os

CONTENT_ORIGIN = "https://mirror.lab.local"

# 指向 compose 的外部 postgres / redis 服務。
# ⚠️ 不設 DATABASES 時,pulp/pulp single-container 會改用容器內建 DB,
#    資料不落在掛載 volume,重建容器即遺失。
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "pulp",
        "USER": "pulp",
        "PASSWORD": os.environ["PULP_DB_PASSWORD"],
        "HOST": "postgres",
        "PORT": 5432,
    }
}
REDIS_HOST = "redis"
REDIS_PORT = 6379
CACHE_ENABLED = True

# lab 內網採匿名可讀(SPEC §3.6):停用 registry token auth,
# /v2/ 可匿名 GET(docker pull、curl、冒煙腳本都不需換 token)。
# 日後開放 container push 或私有 repo 時改為 False 並啟用 /token 端點。
TOKEN_AUTH_DISABLED = True

# 需要鏡像 EL7 等舊 repo 時才加:
# ALLOWED_CONTENT_CHECKSUMS = ["sha1", "sha224", "sha256", "sha384", "sha512"]
```

### 1.3 compose.yml(骨架)

```yaml
services:
  postgres:
    image: docker.io/library/postgres:16
    environment:
      POSTGRES_USER: pulp
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: pulp
    volumes: ["/srv/pulp/pgsql:/var/lib/postgresql/data"]
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U pulp"], interval: 5s, retries: 12 }

  redis:
    image: docker.io/library/redis:7
    healthcheck: { test: ["CMD", "redis-cli", "ping"], interval: 5s, retries: 12 }

  pulp:
    image: docker.io/pulp/pulp:3.114          # 鎖定明確版本 tag,升級走 §2.9 流程
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    environment:
      PULP_WORKERS: "2"
      PULP_DB_PASSWORD: ${DB_PASSWORD}        # settings.py 由環境變數讀入
    volumes:
      - /srv/pulp/storage:/var/lib/pulp
      - /srv/pulp/settings:/etc/pulp
    # 首次啟動要跑 DB migration,start_period 給足時間
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost/pulp/api/v3/status/ >/dev/null"]
      interval: 10s
      retries: 30
      start_period: 300s
    # 除錯需要直連 API 時才打開,且僅綁 localhost:
    # ports: ["127.0.0.1:24817:80"]

  bff:
    build: ../../bff                          # repo 根目錄的 bff/
    environment:
      PULP_URL: http://pulp
      PULP_USERNAME: admin
      PULP_PASSWORD: ${PULP_ADMIN_PASSWORD}
    depends_on:
      pulp: { condition: service_healthy }    # BFF 本身仍需對 Pulp 連線失敗做重試

  frontend:
    build: ../../frontend                     # repo 根目錄的 frontend/
    environment:
      API_BASE_URL: /api

  nginx:
    image: docker.io/library/nginx:1.27
    volumes:
      - ./nginx/mirror.conf:/etc/nginx/conf.d/default.conf:ro
      - /srv/pulp/certs:/etc/nginx/certs:ro
      - /srv/pulp/keys:/srv/keys:ro
    ports: ["80:80", "443:443"]
    depends_on: [pulp, bff, frontend]
```

> compose 檔位於 repo 的 `deploy/compose/`(目錄結構見 SPEC §2.3.1),
> `bff` / `frontend` 的 build context 因此是 `../../`。

### 1.4 Nginx 路由重點(mirror.conf)

```nginx
server {
  listen 443 ssl;
  server_name mirror.lab.local;
  ssl_certificate     /etc/nginx/certs/tls.crt;
  ssl_certificate_key /etc/nginx/certs/tls.key;

  client_max_body_size 0;
  proxy_request_buffering off;
  proxy_buffering off;
  proxy_read_timeout 900s;

  location /            { proxy_pass http://frontend:8080; }
  location /api/        { proxy_pass http://bff:8000; }
  location /pulp/       { proxy_pass http://pulp:80; proxy_set_header Host $host; }
  location /v2/         { proxy_pass http://pulp:80; proxy_set_header Host $host; }
  # token auth 已停用(settings.py TOKEN_AUTH_DISABLED=True);若改回啟用需開這條:
  # location /token     { proxy_pass http://pulp:80; proxy_set_header Host $host; }

  # 發行版 GPG 公鑰(SPEC §4.1 gpgkey= 指向這裡)
  location /keys/       { alias /srv/keys/; autoindex off; }
}
```

### 1.5 啟動與初始化

```bash
cd deploy/compose
export DB_PASSWORD=... PULP_ADMIN_PASSWORD=...
docker compose up -d --build

# 設定 admin 密碼(首次)
docker compose exec pulp pulpcore-manager reset-admin-password --password "$PULP_ADMIN_PASSWORD"

# 安裝 CLI(操作機)
pip install pulp-cli[pygments]
pulp config create --base-url https://mirror.lab.local --username admin --password "$PULP_ADMIN_PASSWORD"
```

### 1.6 驗收

→ 跑 `VERIFICATION.md` §1A(Compose 部署驗證)+ §2–§4(三種格式 E2E)。

---

## 2. Stage 2 — Kubernetes 部署(正式環境)

### 2.1 前置條件

| 項目 | 需求 |
|------|------|
| K8s 版本 | 1.28+(以 pulp-operator 支援表為準) |
| Ingress Controller | ingress-nginx(或等效,需支援 body-size/buffering 註記) |
| cert-manager | 內部 CA ClusterIssuer 已就緒 |
| StorageClass | RWX(NFS/CephFS/Longhorn)**或** S3 相容儲存(MinIO/RGW) |
| 節點資源 | 合計 >= 12 vCPU / 24 GB(含 K8s overhead) |
| 內部 registry | 存放自建 bff/frontend image(bootstrap 不可依賴本 mirror) |

### 2.2 安裝 pulp-operator

```bash
kubectl create namespace pulp-mirror

# 方式 A:OperatorHub / OLM
# 方式 B:Helm
helm repo add pulp-operator https://github.com/pulp/pulp-k8s-resources/raw/main/helm-charts
helm install pulp-operator pulp-operator/pulp-operator -n pulp-mirror
```

✅ `kubectl -n pulp-mirror get deploy pulp-operator-controller-manager` Ready。

### 2.3 建立 Secrets

```bash
kubectl -n pulp-mirror create secret generic pulp-admin-password \
  --from-literal=password='<ADMIN_PASSWORD>'

kubectl -n pulp-mirror create secret generic pulp-postgres \
  --from-literal=POSTGRES_PASSWORD='<DB_PASSWORD>' ...

# 若採 S3 後端
kubectl -n pulp-mirror create secret generic pulp-object-storage \
  --from-literal=s3-access-key-id=... --from-literal=s3-secret-access-key=... \
  --from-literal=s3-bucket-name=pulp --from-literal=s3-endpoint=https://minio.lab.local
```

TLS:由 cert-manager 以 Certificate 資源簽 `mirror.lab.local`。

### 2.4 Pulp 自訂資源 (CR)

`pulp.yaml`(結構示意):

```yaml
apiVersion: repo-manager.pulpproject.org/v1beta2
kind: Pulp
metadata:
  name: mirror
  namespace: pulp-mirror
spec:
  image: quay.io/pulp/pulp-minimal
  image_version: "3.xx"            # 鎖定版本
  admin_password_secret: pulp-admin-password

  api:     { replicas: 2 }
  content: { replicas: 2 }
  worker:  { replicas: 2 }
  web:     { replicas: 1 }         # 視 ingress 策略,可停用改由 ingress 直連

  # 儲存二選一:
  file_storage_storage_class: nfs-rwx      # RWX PVC
  file_storage_access_mode: ReadWriteMany
  file_storage_size: 2Ti
  # object_storage_s3_secret: pulp-object-storage   # 或 S3

  database:
    postgres_storage_class: fast-ssd       # operator 內建 PG;正式環境可改 external_db_secret

  pulp_settings:
    content_origin: "https://mirror.lab.local"
    cache_enabled: true
    token_auth_disabled: true      # 與 Stage 1 一致:lab 內網匿名可讀
```

```bash
kubectl apply -f pulp.yaml
kubectl -n pulp-mirror get pulp mirror -w      # 等 status conditions 全 True
```

### 2.5 部署 BFF 與 Frontend

`bff-deploy.yaml` / `frontend-deploy.yaml` 重點:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: bff, namespace: pulp-mirror }
spec:
  replicas: 2
  selector: { matchLabels: { app: bff } }
  template:
    metadata: { labels: { app: bff } }
    spec:
      containers:
        - name: bff
          image: registry.lab.local/lab/mirror-bff:1.0.0
          env:
            - { name: PULP_URL, value: "http://mirror-api-svc:24817" }  # operator 產生的 svc 名稱以實際為準
            - { name: PULP_USERNAME, value: "admin" }
            - name: PULP_PASSWORD
              valueFrom: { secretKeyRef: { name: pulp-admin-password, key: password } }
          readinessProbe: { httpGet: { path: /api/v1/health, port: 8000 } }
          resources:
            requests: { cpu: 100m, memory: 256Mi }
            limits:   { cpu: "1",  memory: 1Gi }
```

Frontend 同理(nginx-unprivileged serve 靜態檔,port 8080)。各建對應 Service。

### 2.6 Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mirror
  namespace: pulp-mirror
  annotations:
    cert-manager.io/cluster-issuer: lab-ca-issuer
    nginx.ingress.kubernetes.io/proxy-body-size: "0"
    nginx.ingress.kubernetes.io/proxy-request-buffering: "off"
    nginx.ingress.kubernetes.io/proxy-buffering: "off"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "900"
spec:
  ingressClassName: nginx
  tls: [{ hosts: [mirror.lab.local], secretName: mirror-tls }]
  rules:
    - host: mirror.lab.local
      http:
        paths:
          - { path: /api,          pathType: Prefix, backend: { service: { name: bff,      port: { number: 8000 } } } }
          # /pulp/content 必須先於 /pulp:內容下載走 content app,API 走 api svc
          - { path: /pulp/content, pathType: Prefix, backend: { service: { name: mirror-content-svc, port: { number: 24816 } } } }
          - { path: /pulp,         pathType: Prefix, backend: { service: { name: mirror-api-svc,     port: { number: 24817 } } } }
          - { path: /v2,           pathType: Prefix, backend: { service: { name: mirror-content-svc, port: { number: 24816 } } } }
          - { path: /,             pathType: Prefix, backend: { service: { name: frontend, port: { number: 8080 } } } }
```

> content 與 api 的 svc 名稱/拆分方式依 operator 版本不同,
> 以 `kubectl -n pulp-mirror get svc` 實際名稱為準。
> 若改回啟用 token auth,需另加 `/token` path 指向 api svc。

### 2.7 排程與維運性資源

```yaml
apiVersion: batch/v1
kind: CronJob
metadata: { name: sync-rocky9-baseos, namespace: pulp-mirror }
spec:
  schedule: "0 2 * * *"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: sync
              image: curlimages/curl:8
              # $(BFF_TOKEN) 的展開依賴下方 env 宣告;沒宣告會送出字面值
              env:
                - name: BFF_TOKEN
                  valueFrom: { secretKeyRef: { name: bff-service-token, key: token } }
              # 走 cluster 內部 svc,不經 Ingress/TLS hairpin
              args: ["-sf", "-X", "POST", "-H", "Authorization: Bearer $(BFF_TOKEN)",
                     "http://bff:8000/api/v1/repos/rocky9-baseos/sync"]
```

同法建立 `orphan-cleanup` CronJob(每週)。監控加 ServiceMonitor(pulp 有 metrics endpoint 時)+ PVC 用量告警。

### 2.8 資料遷移(Compose → K8s)

1. Compose 端凍結變更(停 UI 寫入操作、確認無 running task)。
2. `pg_dump` Compose 的 PostgreSQL → restore 至 K8s DB。
3. Storage:
   - RWX PVC 方案:`rsync /srv/pulp/storage → PVC 掛載點`(以 job pod 或 NFS 直接搬)。
   - S3 方案:可重建(on_demand 內容會自動再快取),或以 `pulpcore-manager` 匯入。
4. 更新 DNS/`mirror.lab.local` 指向 Ingress VIP。
5. 跑 `VERIFICATION.md` §1B + §2–§4;通過後才下線 Compose 環境。

### 2.9 升級流程(K8s)

1. staging(Compose 或第二 namespace)先升級驗證。
2. 備份 DB;修改 Pulp CR 的 `image_version` → operator 滾動更新並自動 migrate。
3. 升級 BFF/Frontend image tag(`kubectl set image` 或 GitOps)。
4. 跑 VERIFICATION 冒煙(§8 腳本)+ 抽測 §2–4 各一項。
