from urllib.parse import urlparse

import requests
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from llm.base import BaseLLM


def list_models(base_url: str, api_key: str | None = None, timeout: float = 3.0) -> list[str]:
    """Model ids served at an OpenAI-compatible endpoint (its `/v1/models`).

    Works the same for every backend — llama.cpp/llama-swap, Ollama, OpenAI,
    OpenRouter, ... — so the UI populates its model picker from one call.
    """
    headers = {"Authorization": f"Bearer {api_key}"} if api_key and api_key != "none" else {}
    resp = requests.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=timeout)
    resp.raise_for_status()
    return [m["id"] for m in resp.json().get("data", [])]


class OpenAICompatProvider(BaseLLM):
    """The LLM provider: any OpenAI-compatible `/v1` endpoint.

    There is no provider split — llama.cpp/llama-swap, Ollama (`:11434/v1`), and any
    cloud OpenAI-compatible API (OpenAI, OpenRouter, Gemini's OpenAI endpoint, ...)
    are the same client. The engine is pure config — `base_url` + `api_key` + `model`
    — not a code branch. `response_format` json_object holds the scorer's JSON
    contract; `temperature=0` (or as set) keeps scoring reproducible.
    """

    def __init__(
        self,
        base_url: str,
        model: str | None = None,
        temperature: float = 0.0,
        api_key: str | None = None,
    ):
        if not base_url:
            raise ValueError(
                "LLM_BASE_URL is not set — point it at an OpenAI-compatible /v1 endpoint."
            )
        self.base_url = base_url.rstrip("/")
        # Model id: explicit wins; blank → the first model the endpoint serves.
        self.model_name = model or self._first_served_model(api_key)
        self.temperature = temperature
        # Short label (endpoint host:port) for cache filenames + the demo readout.
        self.name = urlparse(self.base_url).netloc or self.base_url

        self.llm = ChatOpenAI(
            model=self.model_name,
            temperature=temperature,
            base_url=self.base_url,
            # Local servers authenticate with nothing, but the client needs a
            # non-empty key, hence "none". Cloud endpoints pass a real key.
            api_key=SecretStr(api_key or "none"),
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    def _first_served_model(self, api_key: str | None) -> str:
        models = list_models(self.base_url, api_key)
        if not models:
            raise ValueError(f"no models served at {self.base_url}; set LLM_MODEL")
        return models[0]

    def generate(self, prompt: str) -> str:
        """Generate a JSON response from the configured endpoint."""
        content = self.llm.invoke(prompt).content
        return content if isinstance(content, str) else str(content)
