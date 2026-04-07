"""Shared LLM calling utility supporting Anthropic and OpenAI."""

import os

import anthropic
import openai


def call_anthropic(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """Call Anthropic Claude API and return the text response."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    messages = [{"role": "user", "content": prompt}]
    kwargs: dict = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": temperature,
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text


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
