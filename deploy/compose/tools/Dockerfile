# dev 工具箱:pulp-cli + jq + curl(seed / smoke 腳本在此容器內執行)
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends jq curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir pulp-cli pulp-cli-deb
CMD ["bash"]
