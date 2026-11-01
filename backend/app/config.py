"""Environment-based configuration. Secrets are read from environment variables only."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_OFFICIAL_SUFFIXES = ("gov.in", "nic.in")


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (no dependency). Never overrides variables already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    ai_api_key: str | None
    ai_model: str
    frontend_origins: tuple
    supabase_url: str | None
    supabase_secret_key: str | None
    review_window_days: int
    official_domain_suffixes: tuple

    @property
    def ai_key_present(self) -> bool:
        return bool(self.ai_api_key)


def load_settings() -> Settings:
    _load_dotenv(PROJECT_ROOT / "backend" / ".env")
    origins = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173,http://127.0.0.1:5173")
    suffixes = os.environ.get("OFFICIAL_DOMAIN_SUFFIXES")
    return Settings(
        ai_api_key=os.environ.get("AI_API_KEY") or None,
        ai_model=os.environ.get("AI_MODEL", "unset"),
        frontend_origins=tuple(o.strip().rstrip("/") for o in origins.split(",") if o.strip()),
        supabase_url=os.environ.get("SUPABASE_URL") or None,
        supabase_secret_key=os.environ.get("SUPABASE_SECRET_KEY") or None,
        review_window_days=int(os.environ.get("REVIEW_WINDOW_DAYS", "90")),
        official_domain_suffixes=tuple(
            s.strip().lower() for s in suffixes.split(",") if s.strip()
        ) if suffixes else DEFAULT_OFFICIAL_SUFFIXES,
    )
