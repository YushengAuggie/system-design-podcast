"""Step 4: Voice Selection — pick voice pair based on season with randomness."""

import random

from pipeline.config import (
    HOST_A_VOICES,
    HOST_B_VOICES,
    SEASON_DEFAULT_PROBABILITY,
    SEASON_VOICES,
)
from pipeline.quality import StepResult


def select_voices(season: int, episode: int) -> tuple[str, str]:
    """Pick a voice pair: 70% season default, 30% random from full pool."""
    if random.random() < SEASON_DEFAULT_PROBABILITY and season in SEASON_VOICES:
        return SEASON_VOICES[season]

    host_a = random.choice(HOST_A_VOICES)
    host_b = random.choice(HOST_B_VOICES)
    return host_a, host_b


def run_voices(season: int, episode: int) -> StepResult:
    """Execute voice selection step."""
    host_a, host_b = select_voices(season, episode)
    return StepResult(
        output={"host_a_voice": host_a, "host_b_voice": host_b},
        passed=True,
        message=f"Selected voices: Host A={host_a}, Host B={host_b}",
        attempt=1,
    )
