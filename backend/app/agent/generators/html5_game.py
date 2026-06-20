"""HTML5 game generator using LLM."""

from dataclasses import dataclass

from app.agent.adapters.base import LLMAdapter
from app.agent.prompts import build_system_prompt, build_user_prompt


@dataclass
class GameGenerationContext:
    """Structured context for game generation."""
    user_prompt: str
    asset_descriptions: list[str] | None = None
    style_preferences: dict | None = None
    game_id: str | None = None


class HTML5GameGenerator:
    """
    Generates a complete, playable HTML5 game using an LLM.

    Takes a natural-language description and optional asset descriptions,
    and produces a self-contained HTML file with embedded CSS and JS.
    """

    def __init__(self, adapter: LLMAdapter):
        self.adapter = adapter

    async def generate(self, context: GameGenerationContext) -> str:
        """
        Generate an HTML5 game from the given context.

        Returns the raw HTML string from the LLM.
        """
        system_prompt = build_system_prompt(context.asset_descriptions)
        user_prompt = build_user_prompt(context.user_prompt, context.style_preferences)

        html_code = await self.adapter.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.8,  # Higher creativity for games
            max_tokens=16000,
        )

        # Clean up common LLM output artifacts
        html_code = self._clean_output(html_code)

        return html_code

    async def fix_errors(self, original_html: str, errors: list[str]) -> str:
        """Ask the LLM to fix validation errors in the generated HTML."""
        from app.agent.prompts import FIX_SYSTEM_PROMPT

        errors_text = "\n".join(f"- {e}" for e in errors)
        prompt = FIX_SYSTEM_PROMPT.format(errors=errors_text, original_code=original_html)

        fixed_html = await self.adapter.generate(
            system_prompt="You are an expert HTML5 game debugger. Fix the errors and output the corrected HTML.",
            user_prompt=prompt,
            temperature=0.5,
            max_tokens=16000,
        )

        return self._clean_output(fixed_html)

    @staticmethod
    def _clean_output(html: str) -> str:
        """Clean common LLM output artifacts from the generated HTML."""
        # Remove markdown HTML fences if present
        html = html.strip()
        if html.startswith("```html"):
            html = html[7:]
        elif html.startswith("```"):
            html = html[3:]
        if html.endswith("```"):
            html = html[:-3]

        # Remove leading/trailing whitespace artifacts
        html = html.strip()

        return html
