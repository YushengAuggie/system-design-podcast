"""Shared utilities: slugify, word count, file I/O."""

import json
import re
from pathlib import Path

from pipeline.config import EPISODES_DIR


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def word_count(text: str) -> int:
    """Count words in text, ignoring markdown headers and formatting."""
    # Strip markdown headers, bold markers, segment dividers
    cleaned = re.sub(r"^#{1,6}\s.*$", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"^---\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\*\*\[Host [AB]\]:\*\*", "", cleaned)
    cleaned = re.sub(r"\*\*", "", cleaned)
    return len(cleaned.split())


def episode_dir(season: int, episode: int, topic: str) -> Path:
    """Get or create the episode output directory."""
    slug = slugify(topic)
    dir_name = f"{episode:02d}-{slug}"
    path = Path(EPISODES_DIR) / dir_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(path: Path, data: dict | list) -> None:
    """Write JSON data to file."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_json(path: Path) -> dict | list:
    """Read JSON data from file."""
    return json.loads(path.read_text())


def save_text(path: Path, text: str) -> None:
    """Write text to file."""
    path.write_text(text)


def load_text(path: Path) -> str:
    """Read text from file."""
    return path.read_text()
