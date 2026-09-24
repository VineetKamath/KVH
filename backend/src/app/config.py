"""Runtime settings, read from the environment (and `.env` at the repo root).

Secrets live only in `.env` (git-ignored). Missing ADMIN_TOKEN fails closed: admin routes reject
every request until a token is configured.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env", override=False)

ORGANISER_DIR = REPO_ROOT / "DynamicPricing"
SOURCE_DB = ORGANISER_DIR / "data" / "APS-02.db"
ENUMS_JSON = ORGANISER_DIR / "data" / "enums.json"
VALIDATOR = ORGANISER_DIR / "tools" / "validate_conformance.py"
DP_SCHEMA = REPO_ROOT / "data-model" / "dp_schema.sqlite.sql"
SEED_DIR = REPO_ROOT / "data-model" / "seed"
VAR_DIR = REPO_ROOT / "var"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
PROMPTS_DIR = Path(__file__).resolve().parent / "ai" / "prompts"


@dataclass(frozen=True)
class Settings:
    db_path: Path
    admin_token: str
    llm_provider: str
    anthropic_api_key: str
    web_origin: str
    auto_reprice_minutes: int
    quote_ttl_seconds: int = 15 * 60


def get_settings() -> Settings:
    provider = os.environ.get("LLM_PROVIDER", "offline").strip().lower()
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if provider not in {"offline", "anthropic"} or (provider == "anthropic" and not key):
        provider = "offline"  # the only secret allowed to fail open: LLM falls back to deterministic templates
    try:
        auto = max(0, int(os.environ.get("AUTO_REPRICE_MINUTES", "0")))
    except ValueError:
        auto = 0
    return Settings(
        db_path=Path(os.environ.get("PIXELMINDS_DB", str(VAR_DIR / "pricing.db"))),
        admin_token=os.environ.get("ADMIN_TOKEN", "").strip(),
        llm_provider=provider,
        anthropic_api_key=key,
        web_origin=os.environ.get("WEB_ORIGIN", "http://localhost:5173").strip(),
        auto_reprice_minutes=auto,
    )
