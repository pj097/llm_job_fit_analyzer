import pytest

from llm.gemini import GeminiProvider
from llm.ollama import OllamaProvider


def test_ollama_provider_init(mocker):
    mocker.patch("llm.ollama.OllamaLLM")

    # Custom values
    provider = OllamaProvider(model="test_model", temperature=0.5)
    assert provider.model_name == "test_model"
    assert provider.temperature == 0.5
    assert provider.name == "ollama:test_model"


def test_ollama_provider_generate(mocker):
    mock_llm_instance = mocker.Mock()
    mock_llm_instance.invoke.return_value = '{"success": true}'
    mocker.patch("llm.ollama.OllamaLLM", return_value=mock_llm_instance)

    provider = OllamaProvider(model="test", temperature=0.5)
    res = provider.generate("test prompt")

    assert res == '{"success": true}'
    mock_llm_instance.invoke.assert_called_once_with("test prompt")


def test_gemini_provider_init(mocker):
    mocker.patch("llm.gemini.genai.Client")

    provider = GeminiProvider(api_key="fake-key")
    assert provider.api_key == "fake-key"
    assert provider.temperature == 0.1


def test_gemini_provider_missing_api_key(mocker):
    # Test ValueError when no API key is provided and settings has none
    mocker.patch("config.settings.settings.gemini_api_key", None)
    with pytest.raises(ValueError) as exc:
        GeminiProvider(api_key=None)
    assert "Gemini API key is not configured" in str(exc.value)


def test_gemini_provider_generate(mocker):
    mock_client = mocker.Mock()
    mock_response = mocker.Mock()
    mock_response.text = '{"fit": 8}'
    mock_client.models.generate_content.return_value = mock_response
    mocker.patch("llm.gemini.genai.Client", return_value=mock_client)

    provider = GeminiProvider(api_key="fake")
    res = provider.generate("test prompt")

    assert res == '{"fit": 8}'
    mock_client.models.generate_content.assert_called_once()
