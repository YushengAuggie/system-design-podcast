"""Configuration constants for the podcast generation pipeline."""

# --- LLM ---
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"

# --- Voice Rotation ---
SEASON_VOICES: dict[int, tuple[str, str]] = {
    1: ("ash", "nova"),
    2: ("echo", "coral"),
    3: ("onyx", "shimmer"),
    4: ("sage", "fable"),
}

HOST_A_VOICES = ["alloy", "echo", "onyx", "ash", "sage"]
HOST_B_VOICES = ["nova", "shimmer", "fable", "coral", "ballad"]

SEASON_DEFAULT_PROBABILITY = 0.70

# --- Word Limits ---
SCRIPT_WORD_MIN = 750
SCRIPT_WORD_MAX = 1500
SCRIPT_WORD_SOFT_MAX = 1650

# --- Audio Limits ---
AUDIO_DURATION_MIN_SEC = 3 * 60
AUDIO_DURATION_MAX_SEC = 12 * 60

# --- Retry Limits ---
SCRIPT_MAX_RETRIES = 3
REVIEW_MAX_CYCLES = 2

# --- Quality Gates ---
RESEARCH_MIN_REFERENCES = 3
RESEARCH_MIN_TALKING_POINTS = 5
VIBE_SCORE_MIN = 7

# --- Segment Count ---
EXPECTED_SEGMENTS = 5

# --- Output Directory ---
EPISODES_DIR = "episodes"
