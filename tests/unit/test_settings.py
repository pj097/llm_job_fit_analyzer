from config.settings import Settings


def test_settings_defaults(monkeypatch):
    # Overwrite potential .env overrides to assert explicit defaults
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)

    # _env_file=None disables .env loading per-instance; pyright can't see this
    # kwarg through pydantic-settings' dynamic constructor — suppression is correct.
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.demo_mode is False
    assert s.default_provider == "ollama"
    assert s.default_model == "gemma4:12b"
    assert s.default_temperature == 1.0


def test_settings_overrides(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEFAULT_PROVIDER", "gemini")
    monkeypatch.setenv("DEFAULT_TEMPERATURE", "0.2")

    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.demo_mode is True
    assert s.default_provider == "gemini"
    assert s.default_temperature == 0.2
