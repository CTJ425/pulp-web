"""BFF 設定;秘密一律來自環境變數(CLAUDE.md 規則)。"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    pulp_url: str = field(default_factory=lambda: os.environ.get("PULP_URL", "http://pulp"))
    pulp_username: str = field(default_factory=lambda: os.environ.get("PULP_USERNAME", "admin"))
    pulp_password: str = field(default_factory=lambda: os.environ["PULP_PASSWORD"])
    # 用戶端設定片段中顯示的對外位址(client-config 用)
    mirror_url: str = field(
        default_factory=lambda: os.environ.get("MIRROR_URL", "https://mirror.lab.local")
    )
