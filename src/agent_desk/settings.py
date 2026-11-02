"""Read desk settings from TOML and then from the environment."""

import os
from pathlib import Path
import tomllib

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Settings(BaseModel):
    """Keep the settings used by the desk."""

    model_config = ConfigDict(extra="forbid")
    bootstrap: str = "localhost:9092"
    refund_limit: float = Field(default=50.0, ge=0, allow_inf_nan=False)
    max_attempts: int = Field(default=3, ge=1)
    backoff_base_s: float = Field(default=1.0, ge=0, allow_inf_nan=False)
    model: str = "openai/qwen"
    api_base: str | None = None
    db_path: Path = Path("data/shop.sqlite")
    checkpoint_path: Path = Path(".agent-desk/checkpoints.sqlite")


def load_settings(path: str | Path = "agent-desk.toml") -> Settings:
    """Load a file if present, then apply named environment overrides."""
    path = Path(path)
    values = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for name in Settings.model_fields:
        key = f"AGENT_DESK_{name.upper()}"
        if key in os.environ:
            values[name] = os.environ[key]
    try:
        return Settings.model_validate(values)
    except ValidationError as exc:
        keys = [f"AGENT_DESK_{str(error['loc'][0]).upper()}" for error in exc.errors()]
        raise ValueError(f"Invalid setting: {', '.join(keys)}") from None
