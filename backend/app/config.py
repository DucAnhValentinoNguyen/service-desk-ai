from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: str = os.getenv("DATABASE_PATH", "data/service-desk.db")
    model_provider: str = os.getenv("MODEL_PROVIDER", "kimi")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    kimi_api_key: str = os.getenv("KIMI_API_KEY", "")
    kimi_base_url: str = os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1")
    kimi_model: str = os.getenv("KIMI_MODEL", "kimi-k3")
    kimi_reasoning_effort: str = os.getenv("KIMI_REASONING_EFFORT", "low")
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
