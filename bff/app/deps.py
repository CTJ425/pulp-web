"""FastAPI 依賴:PulpClient 由 app.state 取得,測試可覆寫。"""

from fastapi import Request

from .config import Settings
from .pulp import PulpClient


def get_pulp(request: Request) -> PulpClient:
    return request.app.state.pulp


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
