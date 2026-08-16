"""
Aletheia global configuration.
Values can be overridden via environment variables.
"""
import os
from pathlib import Path
from typing import Optional


def _load_dotenv(path: Path) -> None:
    """Load the .env file into environment variables (existing values are not overwritten)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).resolve().parent / ".env")


class Config:
    # LLM protocol: anthropic (default) / openai-chat / openai-responses
    PROTOCOL = os.environ.get("LLM_PROTOCOL", "anthropic")

    # Default model for the main agent
    MODEL = os.environ.get("LLM_MODEL", "GLM-5.2")

    # Max tokens per response
    MAX_TOKENS = int(os.environ.get("ALETHEIA_MAX_TOKENS", "4096"))

    API_KEY = os.environ.get("LLM_KEY")

    # When unset, the per-protocol default endpoint (core.llm adapter) is used.
    BASE_URL: Optional[str] = os.environ.get("LLM_BASE_URL")
