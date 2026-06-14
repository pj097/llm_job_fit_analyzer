from google import genai
from google.genai import types

from config.settings import settings
from llm.base import BaseLLM


class GeminiProvider(BaseLLM):
    def __init__(
        self, model: str | None = None, api_key: str | None = None, temperature: float = 0.1
    ):
        # Fallback to settings if not provided in the constructor
        self.api_key = api_key or (
            settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None
        )
        if not self.api_key:
            raise ValueError(
                "Gemini API key is not configured. Provide one in the UI or set GEMINI_API_KEY."
            )
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model or settings.gemini_default_model
        self.temperature = temperature

    def generate(self, prompt: str) -> str:
        """Executes a real-time request. Caching is handled locally in scoring.py."""
        config = types.GenerateContentConfig(
            temperature=self.temperature,
            response_mime_type="application/json",
            # Gemini 3 Feature: Use 'thinking' for better reasoning,
            # but keep it out of the final JSON output.
            thinking_config=types.ThinkingConfig(include_thoughts=False),
        )
        response = self.client.models.generate_content(
            model=self.model_name, contents=prompt, config=config
        )
        return response.text or ""
