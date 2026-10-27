from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
ENV_FILE = ROOT / ".env"


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def main() -> None:
    load_env_file(ENV_FILE)
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))

    from alembic import command
    from alembic.config import Config
    from core.config import get_settings

    settings = get_settings()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    if settings.environment in ("local", "test", "demo"):
        command.upgrade(cfg, "head")

    import uvicorn

    host = os.getenv("CAMPUSPAY_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    print(f"CampusPay starting on http://127.0.0.1:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
