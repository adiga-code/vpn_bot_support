from dataclasses import dataclass

from openai import AsyncOpenAI


@dataclass
class ChatClient:
    client: AsyncOpenAI
    model: str


def make_chat_client(provider: str, openai_key: str, gemini_key: str) -> ChatClient:
    """Build a chat-completion client for the configured provider.

    provider: "openai" (default) or "gemini"
    Both providers expose an OpenAI-compatible API, so the same call
    signatures work without changes in classifier.py / kb.py.
    """
    if provider == "gemini":
        if not gemini_key:
            raise ValueError("GEMINI_API_KEY is required when CHAT_PROVIDER=gemini")
        return ChatClient(
            client=AsyncOpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=gemini_key,
            ),
            model="gemini-2.0-flash",
        )

    return ChatClient(
        client=AsyncOpenAI(api_key=openai_key),
        model="gpt-4o-mini",
    )
