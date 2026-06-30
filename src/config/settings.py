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

    default_provider: str = "ollama"  # ollama | llama | gemini | openai
    default_model: str = "gemma4:12b"
    default_temperature: float = 1.0
    max_attempts: int = 5

    gemini_default_model: str = "gemini-3.5-flash"

    # OpenAI-compatible providers: one ChatOpenAI client over any `/v1` endpoint.
    # `llama` is the local llama.cpp server (llama-server, authenticates with
    # nothing). `openai` is any cloud OpenAI-compatible API (OpenAI, OpenRouter,
    # Together, Groq, ...) — it needs only a base URL, a key, and a model id, all
    # from env, so adding a cloud provider is config, not code.
    llama_base_url: str = "http://localhost:8080/v1"
    openai_base_url: str = ""
    openai_api_key: SecretStr | None = None
    openai_default_model: str = ""

    default_search_pages: int = 10
    use_last_scrape: bool = True

    # Defaulted (instead of required) so the app can start with no .env at all,
    # e.g. in the demo container; validated where they are actually used.
    google_search_params: str = "{}"

    prompt_file: str = ".prompt.txt"

    # Optional so the app can start without secrets (e.g. Ollama-only or demo
    # mode); validated at the point of use instead.
    gemini_api_key: SecretStr | None = None
    serpapi_key: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        secrets_dir=getenv("SECRETS_DIR", "/run/secrets"),
    )


settings = Settings()
