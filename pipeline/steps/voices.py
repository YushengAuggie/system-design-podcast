"""Step 4: Voice Selection — pick voice pair based on season with randomness."""

from __future__ import annotations


import random

from pipeline.config import (
    HOST_A_VOICES,
    HOST_A_VOICES_V3,
    HOST_B_VOICES,
    HOST_B_VOICES_V3,
    SEASON_DEFAULT_PROBABILITY,
    SEASON_VOICES,
    SEASON_VOICES_V3,
    TTS_ENGINE,
)
from pipeline.quality import StepResult


def select_voices(season: int, episode: int) -> tuple[str, str]:
    """Pick a voice pair: 70% season default, 30% random from full pool."""
    if TTS_ENGINE == "elevenlabs-v3":
        voices_map = SEASON_VOICES_V3
        pool_a = HOST_A_VOICES_V3
        pool_b = HOST_B_VOICES_V3
    else:
        voices_map = SEASON_VOICES
        pool_a = HOST_A_VOICES
        pool_b = HOST_B_VOICES

    if random.random() < SEASON_DEFAULT_PROBABILITY and season in voices_map:
        return voices_map[season]

    host_a = random.choice(pool_a)
    host_b = random.choice(pool_b)
    return host_a, host_b


def run_voices(season: int, episode: int) -> StepResult:
    """Execute voice selection step."""
    host_a, host_b = select_voices(season, episode)
    engine_label = f" ({TTS_ENGINE})" if TTS_ENGINE != "openai" else ""
    return StepResult(
        output={"host_a_voice": host_a, "host_b_voice": host_b, "tts_engine": TTS_ENGINE},
        passed=True,
        message=f"Selected voices{engine_label}: Host A={host_a}, Host B={host_b}",
        attempt=1,
    )
