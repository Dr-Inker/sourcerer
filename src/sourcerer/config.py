import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    github_token: str | None
    # Surfaced for visibility/validation only: LiteLLM reads provider keys (OPENROUTER_API_KEY,
    # ANTHROPIC_API_KEY, …) straight from the process environment, so this field is not passed
    # into the client. Set the matching provider key in the environment for SOURCERER_MODEL.
    openrouter_api_key: str | None
    model: str


def get_settings() -> Settings:
    return Settings(
        github_token=os.getenv("GITHUB_TOKEN"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        model=os.getenv("SOURCERER_MODEL", "openrouter/z-ai/glm-5.1"),
    )
