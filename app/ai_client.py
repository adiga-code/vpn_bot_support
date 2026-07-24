from dataclasses import dataclass

from openai import AsyncOpenAI


@dataclass
class ChatClient:
    client: AsyncOpenAI
    model: str


def make_chat_client(provider: str, openai_key: str, gemini_key: str) -> ChatClient | None:
    """Build a chat-completion client for the configured provider.

    provider: "openai" (default) or "gemini"
    Both providers expose an OpenAI-compatible API, so the same call
    signatures work without changes in classifier.py / kb.py.

    Returns None when no key is configured. The LLM here only powers optional
    extras (classification, summaries, KB chunking) and callers already guard
    with `if chat_client`, so a missing key must not stop the app from booting.
    """
    if provider == "gemini":
        if not gemini_key:
            print("[AI] CHAT_PROVIDER=gemini but GEMINI_API_KEY is empty — AI features disabled")
            return None
        return ChatClient(
            client=AsyncOpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=gemini_key,
            ),
            model="gemini-2.0-flash",
        )

    if not openai_key:
        print("[AI] OPENAI_API_KEY is empty — classification, summaries and KB upload disabled")
        return None

    return ChatClient(
        client=AsyncOpenAI(api_key=openai_key),
        model="gpt-4o-mini",
    )
