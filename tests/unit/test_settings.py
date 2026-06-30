from config.settings import Settings


def test_settings_defaults(monkeypatch):
    # Overwrite potential .env overrides to assert explicit defaults
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    # _env_file=None disables .env loading per-instance; pyright can't see this
    # kwarg through pydantic-settings' dynamic constructor — suppression is correct.
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.demo_mode is False
    assert s.llm_base_url == "http://localhost:8080/v1"
    assert s.llm_model == ""
    assert s.llm_api_key is None
    assert s.default_temperature == 1.0


def test_settings_overrides(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen3.5:7b")
    monkeypatch.setenv("DEFAULT_TEMPERATURE", "0.2")

    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.demo_mode is True
    assert s.llm_base_url == "http://localhost:11434/v1"
    assert s.llm_model == "qwen3.5:7b"
    assert s.default_temperature == 0.2
