# lab/mirror-bff(SPEC §2.3.3):multi-stage、non-root、healthcheck /api/v1/health
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# 先解依賴再放程式碼,讓依賴層可快取
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY app ./app
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --system --uid 10001 --create-home bff
WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
USER bff
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=6 --start-period=10s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=2)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
