from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.candidates.symbol_routing import SymbolRecognitionMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="QI_",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://qi:qi@postgres:5432/qi"
    redis_url: str = "redis://redis:6379/0"
    storage_root: Path = Path("/data")
    operator_header: str = "X-QI-Operator"

    tencent_secret_id: str | None = Field(default=None, repr=False)
    tencent_secret_key: str | None = Field(default=None, repr=False)
    tencent_region: str = "ap-guangzhou"

    qwen_api_key: str | None = Field(default=None, repr=False)
    qwen_workspace_id: str | None = None
    qwen_model: str = "qwen3-vl-plus"
    symbol_recognition_mode: SymbolRecognitionMode = "legacy_high_recall"
    provider_cycle_authorization_id: str | None = None
    provider_cycle_authorization_root: Path | None = None

    @model_validator(mode="after")
    def validate_provider_cycle(self) -> Settings:
        cycle_id = self.provider_cycle_authorization_id
        authorization_root = self.provider_cycle_authorization_root
        if (cycle_id is None) != (authorization_root is None):
            raise ValueError(
                "Provider cycle ID and authorization root must be configured together"
            )
        if cycle_id is None:
            return self
        if (
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", cycle_id)
            is None
            or authorization_root is None
            or not authorization_root.is_absolute()
            or self.qwen_model != "qwen3-vl-plus-2025-12-19"
            or self.symbol_recognition_mode != "production_uncertainty"
        ):
            raise ValueError("Provider cycle runtime identity is invalid")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
