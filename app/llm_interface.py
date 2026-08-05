"""LangChain LLM client factory pointed at OpenRouter, with an explicit timeout
and retry count."""

from langchain_openai import ChatOpenAI

from app.core.config import get_settings

# NOTE: direct_query_openrouter_llm() used to live here — a blocking requests.post
# with zero callers. It was the ONLY place config.AGENT_REQUEST_TIMEOUT was ever
# applied, which is why the live ChatOpenAI path had no request deadline at all.
# Deleted; the timeout now sits on the path that actually runs.


def get_llm(
    model_name: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """LangChain LLM pointed at OpenRouter.

    Timeout and retries are set explicitly: an agent loop with no request deadline
    can hang a worker indefinitely on a slow upstream.
    """
    settings = get_settings()

    return ChatOpenAI(
        model=model_name or settings.agent_llm_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=settings.llm_temperature if temperature is None else temperature,
        max_tokens=settings.llm_max_tokens if max_tokens is None else max_tokens,
        timeout=settings.agent_request_timeout,
        max_retries=settings.llm_max_retries,
        default_headers={
            "HTTP-Referer": settings.app_referer,
            "X-Title": settings.app_title,
        },
    )
