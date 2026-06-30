from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from llm.base import BaseLLM


class OpenAICompatProvider(BaseLLM):
    """Any OpenAI-compatible `/v1` endpoint, driven through LangChain's ChatOpenAI.

    The engine is a config choice, not a code branch: local llama.cpp's
    `llama-server` (authenticates with nothing, hence api_key "none") and any cloud
    OpenAI-compatible API (OpenAI, OpenRouter, Together, Groq, ...; real key) are the
    same client with a different base_url / key / model. `response_format`
    json_object holds the scorer's JSON contract, mirroring the Ollama provider's
    `format="json"`.
    """

    def __init__(
        self,
        model: str,
        temperature: float,
        base_url: str,
        api_key: str | None = None,
        label: str = "openai",
    ):
        if not base_url:
            env = "LLAMA_BASE_URL" if label == "llama" else "OPENAI_BASE_URL"
            raise ValueError(
                f"{label} provider needs a base URL. Set {env} to an "
                "OpenAI-compatible /v1 endpoint."
            )
        if not model:
            raise ValueError(
                f"{label} provider needs a model id "
                "(set the model in the UI or OPENAI_DEFAULT_MODEL)."
            )

        self.model_name = model
        self.temperature = temperature
        self.base_url = base_url
        self.name = f"{label}:{model}"

        # Instantiated once so the connection/config is reused across the scoring loop.
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=base_url,
            # llama-server authenticates with nothing, but the client still requires a
            # non-empty key, hence "none". Cloud endpoints pass a real key here.
            api_key=SecretStr(api_key or "none"),
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    def generate(self, prompt: str) -> str:
        """Generate a JSON response from the configured endpoint."""
        content = self.llm.invoke(prompt).content
        return content if isinstance(content, str) else str(content)
