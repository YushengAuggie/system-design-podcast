"""Configuration constants for the podcast generation pipeline."""

# --- LLM ---
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"

# --- TTS Engine ---
# Options: "elevenlabs-v3" (via Poe API) or "openai" (direct OpenAI TTS)
TTS_ENGINE = "elevenlabs-v3"

# ElevenLabs v3 settings (via Poe API)
ELEVENLABS_V3_MODEL = "ElevenLabs-v3"
ELEVENLABS_V3_CHAR_LIMIT = 4800  # 5000 hard limit, keep buffer

# --- Voice Rotation ---
# ElevenLabs v3 voice pairs (used when TTS_ENGINE = "elevenlabs-v3")
# Locked to Liam + Bradford — proven combo with clear voice distinction.
# Do NOT randomize; other v3 voice combos may collapse to a single voice.
SEASON_VOICES_V3: dict[int, tuple[str, str]] = {
    1: ("Liam", "Bradford"),
    2: ("Liam", "Bradford"),
    3: ("Liam", "Bradford"),
    4: ("Liam", "Bradford"),
}

HOST_A_VOICES_V3 = ["Liam"]
HOST_B_VOICES_V3 = ["Bradford"]

# OpenAI voice pairs (used when TTS_ENGINE = "openai")
SEASON_VOICES: dict[int, tuple[str, str]] = {
    1: ("echo", "nova"),
    2: ("echo", "nova"),
    3: ("echo", "nova"),
    4: ("echo", "nova"),
}

HOST_A_VOICES = ["alloy", "echo", "onyx", "ash", "sage"]
HOST_B_VOICES = ["nova", "shimmer", "fable", "coral", "ballad"]

# Always use season default voices (no randomization for v3)
SEASON_DEFAULT_PROBABILITY = 1.0

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
DIAGRAM_MAX_RETRIES = 2
DIAGRAM_REVIEW_MAX_CYCLES = 2

# --- Diagram Screenshot ---
DIAGRAM_SCREENSHOT_WIDTH = 1280
DIAGRAM_SCREENSHOT_HEIGHT = 720

# --- Quality Gates ---
RESEARCH_MIN_REFERENCES = 3
RESEARCH_MIN_TALKING_POINTS = 5
VIBE_SCORE_MIN = 7

# --- Segment Count ---
EXPECTED_SEGMENTS = 5

# --- Output Directory ---
EPISODES_DIR = "episodes"

# --- Website ---
WEBSITE_DIR = "docs"
WEBSITE_URL = "https://yushengauggie.github.io/byte-by-design"

# --- YouTube Upload ---
YOUTUBE_CATEGORY_ID = "28"          # Science & Technology
YOUTUBE_DEFAULT_PRIVACY = "unlisted"  # User manually publishes
YOUTUBE_MIN_VIDEO_SIZE_BYTES = 100_000  # 100 KB sanity floor

# --- Podcast Feed ---
PODCAST_TITLE = "Byte by Design"
PODCAST_AUTHOR = "Yusheng Ding"
PODCAST_WEBSITE = "https://yushengauggie.github.io/byte-by-design"
PODCAST_DESCRIPTION = "Two AI hosts break down system design in bite-sized episodes — like overhearing two senior engineers whiteboarding over coffee. Each episode tackles a real interview topic: from URL shorteners to LLM serving platforms, covering requirements, architecture, trade-offs, and how companies like Netflix, Stripe, and Google actually built it. 5-10 minutes, no fluff, interview-ready."
PODCAST_FEED_FILE = "feed.xml"
PODCAST_IMAGE_URL = "https://yushengauggie.github.io/byte-by-design/cover.jpg"
PODCAST_GITHUB_REPO = "YushengAuggie/byte-by-design"
