# Pulp 設定(dynaconf python loader;環境變數 PULP_* 優先於本檔)
# 對應 docs/DEPLOYMENT.md §1.2。dev 環境由 compose 以 PULP_CONTENT_ORIGIN 覆寫。
import os

CONTENT_ORIGIN = "https://mirror.lab.local"

# 指向 compose 的外部 postgres / redis 服務。
# 不設 DATABASES 時 pulp/pulp single-container 會用容器內建 DB,資料不落在 volume。
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

# lab 內網匿名可讀(SPEC §3.6);開放 container push 時改 False 並啟用 /token
TOKEN_AUTH_DISABLED = True

# 需要鏡像 EL7 等舊 repo 時才放寬(docs/TROUBLESHOOTING.md §3.4):
# ALLOWED_CONTENT_CHECKSUMS = ["sha1", "sha224", "sha256", "sha384", "sha512"]
