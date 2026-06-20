"""Abstract base class for LLM adapters."""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMAdapter(ABC):
    """
    Abstract interface for LLM providers.

    Implementations:
    - ClaudeAdapter (Anthropic)
    - OpenAIAdapter (OpenAI)

    To add a new provider, subclass this and implement all methods.
    Then register in adapters/__init__.py factory.
    """

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> str:
        """Generate a complete text response from the LLM."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> AsyncIterator[str]:
        """Generate a streaming text response from the LLM."""
        ...

    @abstractmethod
    async def describe_image(self, image_url: str) -> str:
        """Describe an image using vision capabilities."""
        ...
