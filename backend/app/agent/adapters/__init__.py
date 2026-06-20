"""LLM Adapter factory."""

from app.config import settings
from app.agent.adapters.base import LLMAdapter
from app.agent.adapters.claude_adapter import ClaudeAdapter
from app.agent.adapters.openai_adapter import OpenAIAdapter
from app.agent.adapters.deepseek_adapter import DeepSeekAdapter


def create_adapter() -> LLMAdapter:
    """
    Factory: create the configured LLM adapter instance.

    Reads LLM_PROVIDER from settings and returns the appropriate implementation.
    Supported: claude | openai | deepseek | none
    """
    provider = settings.llm_provider.lower()

    if provider == "claude":
        return ClaudeAdapter(
            api_key=settings.llm_api_key,
            model=settings.llm_model or "claude-sonnet-4-20250514",
        )
    elif provider == "openai":
        return OpenAIAdapter(
            api_key=settings.llm_api_key,
            model=settings.llm_model or "gpt-4o",
            base_url=settings.llm_api_base_url or None,
        )
    elif provider == "deepseek":
        return DeepSeekAdapter(
            api_key=settings.llm_api_key,
            model=settings.llm_model or "deepseek-chat",
        )
    elif provider == "none":
        raise ValueError(
            "LLM_PROVIDER is set to 'none'. Set LLM_PROVIDER and LLM_API_KEY in .env to enable AI generation."
        )
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: {provider}. Use 'claude', 'openai', or 'deepseek'."
        )


__all__ = ["LLMAdapter", "ClaudeAdapter", "OpenAIAdapter", "DeepSeekAdapter", "create_adapter"]
