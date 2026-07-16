from dataclasses import dataclass

from openai import AsyncOpenAI


@dataclass
class ChatClient:
    client: AsyncOpenAI
    model: str


def make_chat_client(provider: str, openai_key: str, gemini_key: str,
                     model_override: str = "") -> ChatClient:
    """Build a chat-completion client for the configured provider.

    provider: "openai" (default) or "gemini"
    model_override: CHAT_MODEL from .env — replaces the provider default for
    KB chunking, message classification and dialog summaries.
    Both providers expose an OpenAI-compatible API, so the same call
    signatures work without changes in classifier.py / kb.py.
    """
    model_override = (model_override or "").strip()
    if provider == "gemini":
        if not gemini_key:
            raise ValueError("GEMINI_API_KEY is required when CHAT_PROVIDER=gemini")
        return ChatClient(
            client=AsyncOpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=gemini_key,
            ),
            model=model_override or "gemini-2.0-flash",
        )

    return ChatClient(
        client=AsyncOpenAI(api_key=openai_key),
        model=model_override or "gpt-4o-mini",
    )
