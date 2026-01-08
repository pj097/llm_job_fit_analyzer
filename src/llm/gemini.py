import json
from google import genai
from google.genai import types
from llm.base import BaseLLM
from config.settings import settings

class GeminiProvider(BaseLLM):
    def __init__(self, model: str | None = None, api_key: str | None = None, temperature: float = 0.1):
        # Fallback to settings if not provided in the constructor
        self.api_key = api_key or settings.gemini_api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model or settings.gemini_default_model
        self.temperature = temperature

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Executes a real-time request. 
        Note: Caching is handled locally in scoring.py, so we don't pass cache_name here.
        """
        config = types.GenerateContentConfig(
            temperature=self.temperature,
            response_mime_type="application/json",
            # Gemini 3 Feature: Use 'thinking' for better reasoning, 
            # but keep it out of the final JSON output.
            thinking_config=types.ThinkingConfig(include_thoughts=False)
        )
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config
        )
        return response.text

    def submit_batch(self, prompts: list[str]):
        """
        Submits multiple job descriptions at once for 50% cost savings.
        The results are retrieved later and saved to your local disk cache.
        """
        # Format the prompts into the specific 'inline' request structure Gemini expects
        requests = [
            {"contents": [{"role": "user", "parts": [{"text": p}]}]} 
            for p in prompts
        ]
        
        return self.client.batches.create(
            model=self.model_name,
            src=requests,
            config=types.CreateBatchJobConfig(
                display_name="job_scoring_run"
            )
        )

    def get_batch_status(self, batch_id: str):
        """Helper to check if a batch job is finished."""
        return self.client.batches.get(name=batch_id)