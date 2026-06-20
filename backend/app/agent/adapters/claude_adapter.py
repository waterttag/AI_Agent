"""Anthropic Claude LLM adapter."""

from typing import AsyncIterator

from anthropic import AsyncAnthropic

from app.agent.adapters.base import LLMAdapter


class ClaudeAdapter(LLMAdapter):
    """LLM adapter for Anthropic Claude models."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        super().__init__(api_key, model)
        self.client = AsyncAnthropic(api_key=api_key)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> str:
        """Generate a complete response using Claude's Messages API."""
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        )
        # Extract text from the first content block
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> AsyncIterator[str]:
        """Stream tokens from Claude."""
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def describe_image(self, image_url: str) -> str:
        """Describe an image using Claude's vision capability."""
        # Fetch the image data first
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            image_data = resp.content

        import base64

        b64_image = base64.b64encode(image_data).decode("utf-8")
        media_type = resp.headers.get("content-type", "image/png")

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Describe this image in detail, focusing on visual elements relevant for a game: colors, shapes, characters, objects, style, and any animation cues. Keep under 200 words.",
                        },
                    ],
                }
            ],
        )
        for block in response.content:
            if block.type == "text":
                return block.text
        return "No description available."
