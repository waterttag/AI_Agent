"""DeepSeek LLM adapter.

DeepSeek API is OpenAI-compatible — just a different base_url.
Vision: deepseek-chat does NOT support image inputs natively.
We provide a text-only fallback for describe_image().
"""

from typing import AsyncIterator

from app.agent.adapters.openai_adapter import OpenAIAdapter


DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekAdapter(OpenAIAdapter):
    """LLM adapter for DeepSeek models (OpenAI-compatible API).

    Recommended models:
    - deepseek-chat      — general purpose, fast, cost-effective
    - deepseek-reasoner  — reasoning-heavy tasks (slower, higher quality)
    """

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=DEEPSEEK_BASE_URL,
        )

    async def describe_image(self, image_url: str) -> str:
        """Describe an image. DeepSeek-chat lacks native vision, so we
        return a generic description. The game prompt will rely on the
        user's text description of any uploaded assets."""
        # DeepSeek-chat is text-only; use the filename as context
        filename = image_url.split("/")[-1] if "/" in image_url else image_url
        return (
            f"An uploaded asset file ({filename}). "
            "DeepSeek does not support image analysis; "
            "the game should be generated based on the user's text description."
        )
