import pytest

from llm.openai_compat import OpenAICompatProvider


def test_provider_init_with_explicit_model(mocker):
    mocker.patch("llm.openai_compat.ChatOpenAI")
    # An explicit model means the endpoint is never queried.
    spy = mocker.patch("llm.openai_compat.list_models")

    provider = OpenAICompatProvider(
        base_url="http://endpoint:8080/v1",
        model="gpt-4o-mini",
        temperature=0.2,
        api_key="k",
    )
    assert provider.model_name == "gpt-4o-mini"
    assert provider.base_url == "http://endpoint:8080/v1"
    assert provider.name == "endpoint:8080"  # netloc, used for cache + demo readout
    spy.assert_not_called()


def test_provider_resolves_first_served_model(mocker):
    mocker.patch("llm.openai_compat.ChatOpenAI")
    mocker.patch("llm.openai_compat.list_models", return_value=["served-a", "served-b"])

    provider = OpenAICompatProvider(base_url="http://endpoint/v1")
    assert provider.model_name == "served-a"


def test_provider_requires_base_url(mocker):
    mocker.patch("llm.openai_compat.ChatOpenAI")
    with pytest.raises(ValueError) as exc:
        OpenAICompatProvider(base_url="")
    assert "LLM_BASE_URL" in str(exc.value)


def test_provider_raises_when_no_model_served(mocker):
    mocker.patch("llm.openai_compat.ChatOpenAI")
    mocker.patch("llm.openai_compat.list_models", return_value=[])
    with pytest.raises(ValueError) as exc:
        OpenAICompatProvider(base_url="http://endpoint/v1")
    assert "no models served" in str(exc.value)


def test_provider_generate(mocker):
    mock_message = mocker.Mock()
    mock_message.content = '{"fit": 9}'
    mock_instance = mocker.Mock()
    mock_instance.invoke.return_value = mock_message
    mocker.patch("llm.openai_compat.ChatOpenAI", return_value=mock_instance)

    provider = OpenAICompatProvider(base_url="http://endpoint/v1", model="m")
    res = provider.generate("test prompt")

    assert res == '{"fit": 9}'
    mock_instance.invoke.assert_called_once_with("test prompt")


def test_list_models_parses_openai_shape(mocker):
    resp = mocker.Mock()
    resp.json.return_value = {"data": [{"id": "a"}, {"id": "b"}]}
    get = mocker.patch("llm.openai_compat.requests.get", return_value=resp)

    from llm.openai_compat import list_models

    assert list_models("http://endpoint/v1", api_key="secret") == ["a", "b"]
    # Cloud key becomes a bearer header; "none"/empty would not.
    _, kwargs = get.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
