from langchain_ollama import OllamaLLM
from llm.base import BaseLLM
from config.settings import settings

class OllamaProvider(BaseLLM):
    def __init__(self, model: str, temperature: float):
        self.model_name = model
        self.temperature = temperature
        self.name = f"ollama:{model}"
        
        # Instantiate once here to keep the model loaded in memory during the scoring loop
        self.llm = OllamaLLM(
            model=self.model_name,
            temperature=self.temperature,
            # Ensure Ollama returns valid JSON if your prompt requests it
            format="json" 
        )

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generates a response using Ollama.
        **kwargs allows this method to accept 'cache_name' or other 
        provider-specific arguments without crashing.
        """
        # Ollama automatically handles its own internal "Prefix Caching," 
        # so we don't need to do anything with kwargs here.
        return self.llm.invoke(prompt)