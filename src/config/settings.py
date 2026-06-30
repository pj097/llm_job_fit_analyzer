from os import getenv
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LLM Job Fit Analyzer"
    debug: bool = False

    project_root: Path = Path(__file__).resolve().parents[1]
    results_dir: Path = Field(default_factory=lambda: Path("search_results"))

    # Demo mode: replays recorded fixtures instead of hitting external services.
    demo_mode: bool = False
    fixtures_dir: Path = Field(default_factory=lambda: Path("demo/fixtures"))

    # The LLM is any OpenAI-compatible `/v1` endpoint — llama.cpp/llama-swap, Ollama
    # (`:11434/v1`), OpenAI, OpenRouter, Gemini's OpenAI endpoint, ... There is no
    # provider split: switching engine is just these three values.
    #   llm_base_url — the endpoint (e.g. http://localhost:8080/v1 for llama-swap).
    #   llm_api_key  — bearer key for cloud; unset (→ "none") for local servers.
    #   llm_model    — model id; blank picks the first the endpoint serves.
    llm_base_url: str = "http://localhost:8080/v1"
    llm_api_key: SecretStr | None = None
    llm_model: str = ""

    default_temperature: float = 1.0
    max_attempts: int = 5

    default_search_pages: int = 10
    use_last_scrape: bool = True

    # Defaulted (instead of required) so the app can start with no .env at all,
    # e.g. in the demo container; validated where they are actually used.
    google_search_params: str = "{}"

    prompt_file: str = ".prompt.txt"

    # Optional so the app can start without secrets (e.g. a local LLM or demo
    # mode); validated at the point of use instead.
    serpapi_key: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        secrets_dir=getenv("SECRETS_DIR", "/run/secrets"),
        # Treat a blank value in .env (e.g. `LLM_API_KEY=`) as unset rather than an
        # empty string. Without this, a blank placeholder would *shadow* a secret
        # injected via secrets_dir (podman/docker secrets at /run/secrets), since
        # dotenv outranks the secrets source — so the injected key would be ignored.
        env_ignore_empty=True,
    )


settings = Settings()
