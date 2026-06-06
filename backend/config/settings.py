from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_IS_TEST = os.getenv("APP_ENV", "") == "test"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ────────────────────────────────────────────────────
    # Railway sets RAILWAY_ENVIRONMENT=production automatically; fall back to APP_ENV
    app_env: str = Field(
        default_factory=lambda: (
            os.getenv("RAILWAY_ENVIRONMENT")
            or os.getenv("APP_ENV", "development")
        )
    )
    log_level: str = "INFO"
    # Required in all non-test environments (min 32 chars)
    secret_key: str = Field(default="")
    # API bearer token — required in all non-test environments
    api_key: str = Field(default="")

    @field_validator("secret_key")
    @classmethod
    def _require_secret_key(cls, v: str) -> str:
        if _IS_TEST:
            return v or "test-secret-key-32-chars-minimum!!"
        if not v:
            raise ValueError(
                "SECRET_KEY must be set in environment (min 32 chars). "
                "Generate: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("api_key")
    @classmethod
    def _require_api_key(cls, v: str) -> str:
        if _IS_TEST:
            return v or "test-api-key"
        if not v:
            raise ValueError(
                "API_KEY must be set in environment. "
                "Generate: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    # ── OpenAI ─────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # ── Exchange ───────────────────────────────────────────────
    exchange_id: str = "binance"
    exchange_api_key: str = ""
    exchange_api_secret: str = ""
    exchange_sandbox: bool = True

    # ── Database ───────────────────────────────────────────────
    # Railway PostgreSQL plugin exports DATABASE_URL as postgres:// — auto-fixed below
    database_url: str = "postgresql+asyncpg://sfomo:sfomo@localhost:5432/sfomo"

    @field_validator("database_url")
    @classmethod
    def _fix_database_url(cls, v: str) -> str:
        # Railway (and Heroku-style platforms) export postgres:// or postgresql://
        # SQLAlchemy asyncpg driver requires postgresql+asyncpg://
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

    # ── Redis ──────────────────────────────────────────────────
    # Railway Redis plugin exports REDIS_URL in a compatible format
    redis_url: str = "redis://localhost:6379/0"

    # ── Qdrant ─────────────────────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # ── External Data ──────────────────────────────────────────
    coinglass_api_key: str = ""
    glassnode_api_key: str = ""

    # ── Trading ────────────────────────────────────────────────
    initial_capital: float = 10_000.0
    base_currency: str = "USDT"
    max_open_positions: int = 5
    risk_per_trade: float = 0.005
    max_portfolio_drawdown: float = 0.15
    leverage: int = 1

    # ── Strategy Weights ───────────────────────────────────────
    weight_trend_following: float = 0.30
    weight_momentum_breakout: float = 0.25
    weight_mean_reversion: float = 0.20
    weight_volatility_arb: float = 0.15
    weight_portfolio_rotation: float = 0.10

    # ── Pairs & Timeframe ──────────────────────────────────────
    trading_pairs_raw: str = Field(
        default="BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,AVAX/USDT",
        alias="TRADING_PAIRS",
    )
    timeframe: str = "1h"

    # ── CORS ───────────────────────────────────────────────────
    # Comma-separated list of allowed origins.
    # On Railway: set CORS_ORIGINS=https://your-frontend.up.railway.app
    cors_origins_raw: str = Field(
        default="http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    @property
    def trading_pairs(self) -> List[str]:
        return [p.strip() for p in self.trading_pairs_raw.split(",")]

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
