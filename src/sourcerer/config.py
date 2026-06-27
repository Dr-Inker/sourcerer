import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    github_token: str | None
    openrouter_api_key: str | None
    model: str


def get_settings() -> Settings:
    return Settings(
        github_token=os.getenv("GITHUB_TOKEN"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        model=os.getenv("SOURCERER_MODEL", "anthropic/claude-sonnet-4.6"),
    )
