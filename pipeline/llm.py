"""Shared LLM calling utility supporting Poe (OpenAI-compatible) and OpenAI TTS."""

from __future__ import annotations


import os

import openai

# --- Poe API (OpenAI-compatible) ---
POE_BASE_URL = "https://api.poe.com/v1"
POE_DEFAULT_MODEL = "claude-sonnet-4.5"


def _get_poe_client() -> openai.OpenAI:
    """Create an OpenAI client pointed at Poe's API."""
    api_key = os.environ.get("POE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "POE_API_KEY not set. Add it to your .env or environment variables."
        )
    return openai.OpenAI(api_key=api_key, base_url=POE_BASE_URL)


def call_anthropic(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """Call Claude via Poe's OpenAI-compatible API and return the text response."""
    client = _get_poe_client()
    model = os.environ.get("POE_MODEL", POE_DEFAULT_MODEL)

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content


def call_openai_tts(
    text: str,
    voice: str,
    model: str = "gpt-4o-mini-tts",
    instructions: str = "",
) -> bytes:
    """Call OpenAI TTS API and return raw audio bytes (MP3)."""
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    kwargs: dict = {
        "model": model,
        "voice": voice,
        "input": text,
    }
    if instructions:
        kwargs["instructions"] = instructions
    response = client.audio.speech.create(**kwargs)
    return response.content
