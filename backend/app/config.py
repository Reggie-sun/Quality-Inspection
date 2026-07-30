from functools import lru_cache
from pathlib import Path

from pydantic import Field
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
