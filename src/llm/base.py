from abc import ABC, abstractmethod


class BaseLLM(ABC):
    name: str

    @abstractmethod
    def generate(self, prompt: str) -> str:
        raise NotImplementedError

