from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: str = os.getenv("DATABASE_PATH", "data/service-desk.db")
    model_provider: str = os.getenv("MODEL_PROVIDER", "auto")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    ai_timeout_seconds: float = float(os.getenv("AI_TIMEOUT_SECONDS", "20"))
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:3005,http://127.0.0.1:3005"
        ).split(",")
        if origin.strip()
    )

    def ensure_parent(self) -> None:
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
