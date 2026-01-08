from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    app_name: str = "LLM Job Fit Analyzer"
    debug: bool = False

    project_root: Path = Path(__file__).resolve().parents[1]
    results_dir: Path = Field(default_factory=lambda: Path("search_results"))

    default_provider: str = "ollama"   # ollama | gemini
    default_model: str = "llama3.1:8b"
    default_temperature: float = 1.0
    max_attempts: int = 5

    gemini_api_key: str = Field(...)
    gemini_default_model: str = Field(...)

    default_search_pages: int = 10
    use_last_scrape: bool = True

    serpapi_key: str = Field(...)
    google_search_params: str = Field(...)

    exclude_title_keywords: list[str] = Field(...)
    prompt_file: str = Field(...)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

settings = Settings()
