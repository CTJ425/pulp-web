"""BFF 入口;所有路由掛在 /api/v1(nginx 以 /api/ 轉發過來)。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .pulp import PulpClient, PulpError
from .routers import repos, system, tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.settings = settings
    app.state.pulp = PulpClient(settings.pulp_url, settings.pulp_username, settings.pulp_password)
    yield
    await app.state.pulp.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="lab-mirror BFF", lifespan=lifespan)

    @app.exception_handler(PulpError)
    async def pulp_error_handler(_: Request, exc: PulpError) -> JSONResponse:
        # Pulp 4xx 多半是使用者輸入問題,照實轉;5xx 一律 502
        status = exc.status if 400 <= exc.status < 500 else 502
        return JSONResponse(status_code=status, content={"detail": exc.detail})

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {"status": "ok"}

    for router in (repos.router, tasks.router, system.router):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
