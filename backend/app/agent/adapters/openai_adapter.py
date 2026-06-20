"""OpenAI GPT LLM adapter."""

from typing import AsyncIterator

from openai import AsyncOpenAI

from app.agent.adapters.base import LLMAdapter


class OpenAIAdapter(LLMAdapter):
    """LLM adapter for OpenAI-compatible APIs (GPT, DeepSeek, etc.)."""

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None):
        super().__init__(api_key, model)
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**kwargs)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> str:
        """Generate a complete response using OpenAI's Chat API."""
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> AsyncIterator[str]:
        """Stream tokens from OpenAI."""
        stream = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def describe_image(self, image_url: str) -> str:
        """Describe an image using GPT-4o vision."""
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                        {
                            "type": "text",
                            "text": "Describe this image in detail, focusing on visual elements relevant for a game: colors, shapes, characters, objects, style, and any animation cues. Keep under 200 words.",
                        },
                    ],
                }
            ],
        )
        return response.choices[0].message.content or "No description available."
