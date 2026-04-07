"""Step 7: YouTube Upload — convert MP3 → MP4 and upload to YouTube."""

import os
import re
import shutil
import subprocess
from pathlib import Path

from pipeline.config import (
    YOUTUBE_CATEGORY_ID,
    YOUTUBE_DEFAULT_PRIVACY,
    YOUTUBE_MIN_VIDEO_SIZE_BYTES,
)
from pipeline.quality import StepResult


# --- Branded fallback image (1280x720, dark background) ---
# Used when no rendered diagram PNG is available.
FALLBACK_IMAGE_PATH = Path(__file__).parent.parent / "assets" / "branded_thumbnail.png"


def _slugify(text: str) -> str:
    """Convert a topic string to a URL/tag-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug


# ---------------------------------------------------------------------------
# Metadata generation
# ---------------------------------------------------------------------------


def _build_title(topic: str, season: int, episode: int) -> str:
    """Generate YouTube video title."""
    return f"System Design: {topic} | S{season:02d}E{episode:02d}"


def _build_description(topic: str, research: dict) -> str:
    """Generate video description from research data."""
    lines: list[str] = []

    summary = research.get("summary", f"A deep dive into {topic}.")
    lines.append(summary)
    lines.append("")

    talking_points = research.get("talking_points", [])
    if talking_points:
        lines.append("🗂 What we cover:")
        for pt in talking_points:
            lines.append(f"  • {pt}")
        lines.append("")

    refs = research.get("real_world_references", [])
    if refs:
        lines.append("📚 References & further reading:")
        for ref in refs:
            company = ref.get("company", "")
            detail = ref.get("detail", "")
            url = ref.get("url", "")
            if url:
                lines.append(f"  • {company}: {detail} — {url}")
            else:
                lines.append(f"  • {company}: {detail}")
        lines.append("")

    interview_angles = research.get("interview_angles", [])
    if interview_angles:
        lines.append("🎯 Interview angles:")
        for angle in interview_angles:
            lines.append(f"  • {angle}")
        lines.append("")

    lines.append("---")
    lines.append("System Design Podcast | Building scalable systems, one episode at a time.")

    return "\n".join(lines)


def _build_tags(topic: str, research: dict) -> list[str]:
    """Generate tags list for the video."""
    topic_slug = _slugify(topic)
    base_tags = [
        "system design",
        "software engineering",
        "interview prep",
        "distributed systems",
        "software architecture",
        "tech podcast",
        topic_slug,
        topic.lower(),
    ]

    # Add architecture component names as tags
    for component in research.get("architecture_components", []):
        tag = component.lower().strip()
        if tag and tag not in base_tags:
            base_tags.append(tag)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_tags: list[str] = []
    for tag in base_tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    # YouTube allows up to 500 characters total across all tags
    return unique_tags[:20]


# ---------------------------------------------------------------------------
# MP3 → MP4 conversion
# ---------------------------------------------------------------------------


def _find_thumbnail(episode_dir: Path, research: dict) -> Path | None:
    """Locate the best available thumbnail image.

    Priority:
    1. Rendered PNG from Mermaid diagram (diagram.png)
    2. Branded fallback image
    """
    diagram_png = episode_dir / "diagram.png"
    if diagram_png.exists() and diagram_png.stat().st_size > 0:
        return diagram_png

    if FALLBACK_IMAGE_PATH.exists():
        return FALLBACK_IMAGE_PATH

    return None


def _create_mp4(episode_dir: Path, research: dict) -> tuple[Path, str]:
    """Convert episode MP3 + thumbnail image into an MP4 using ffmpeg.

    Returns:
        (mp4_path, message) on success.

    Raises:
        RuntimeError: if ffmpeg is unavailable or conversion fails.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg is not installed or not on PATH. "
            "Install it via `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)."
        )

    mp3_path = episode_dir / "episode.mp3"
    if not mp3_path.exists():
        raise RuntimeError(f"Episode MP3 not found: {mp3_path}")

    thumbnail = _find_thumbnail(episode_dir, research)
    if thumbnail is None:
        raise RuntimeError(
            "No thumbnail image available. Neither diagram.png nor a fallback branded "
            "image was found. Run the diagram step first, or add a branded thumbnail at "
            f"{FALLBACK_IMAGE_PATH}."
        )

    mp4_path = episode_dir / "episode.mp4"

    cmd = [
        "ffmpeg",
        "-y",                   # overwrite output without asking
        "-loop", "1",
        "-i", str(thumbnail),
        "-i", str(mp3_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(mp4_path),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg conversion failed (exit {result.returncode}):\n{result.stderr[-2000:]}"
        )

    return mp4_path, f"MP4 created: {mp4_path.name} ({mp4_path.stat().st_size // 1024} KB)"


# ---------------------------------------------------------------------------
# YouTube upload
# ---------------------------------------------------------------------------


def _build_youtube_client():  # type: ignore[return]
    """Build an authenticated YouTube API client from environment variables.

    Required env vars:
        YOUTUBE_CLIENT_ID
        YOUTUBE_CLIENT_SECRET
        YOUTUBE_REFRESH_TOKEN

    Raises:
        RuntimeError: if any required env var is missing or import fails.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "google-api-python-client or google-auth packages are not installed. "
            "Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        ) from exc

    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    missing = [
        name
        for name, val in [
            ("YOUTUBE_CLIENT_ID", client_id),
            ("YOUTUBE_CLIENT_SECRET", client_secret),
            ("YOUTUBE_REFRESH_TOKEN", refresh_token),
        ]
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing YouTube credentials env vars: {', '.join(missing)}. "
            "Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN."
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )

    return build("youtube", "v3", credentials=creds)


def _upload_to_youtube(
    mp4_path: Path,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = YOUTUBE_CATEGORY_ID,
    privacy_status: str = YOUTUBE_DEFAULT_PRIVACY,
) -> str:
    """Upload an MP4 to YouTube and return the video URL.

    Raises:
        RuntimeError: on credential/import issues or API error.
    """
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "google-api-python-client is not installed. "
            "Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        ) from exc

    youtube = _build_youtube_client()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
        },
    }

    media = MediaFileUpload(
        str(mp4_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5,  # 5 MB chunks
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    print("  Uploading to YouTube...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Upload progress: {pct}%")

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    return url


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_mp4(mp4_path: Path) -> tuple[bool, str]:
    """Validate the generated MP4 file."""
    if not mp4_path.exists():
        return False, f"MP4 file was not created: {mp4_path}"

    size = mp4_path.stat().st_size
    if size < YOUTUBE_MIN_VIDEO_SIZE_BYTES:
        return (
            False,
            f"MP4 too small: {size} bytes (minimum {YOUTUBE_MIN_VIDEO_SIZE_BYTES} bytes). "
            "Likely an ffmpeg error.",
        )

    return True, f"MP4 valid: {mp4_path.name} ({size // 1024} KB)"


# ---------------------------------------------------------------------------
# Public step entry point
# ---------------------------------------------------------------------------


def run_youtube(
    episode_dir: Path,
    topic: str,
    season: int,
    episode: int,
    research: dict,
    dry_run: bool = False,
) -> StepResult:
    """Execute the YouTube step: MP3 → MP4 conversion, then upload.

    Args:
        episode_dir: Path to the episode output directory.
        topic: Human-readable topic name.
        season: Season number.
        episode: Episode number.
        research: Research data dict (used for metadata generation).
        dry_run: If True, generate the MP4 but skip the YouTube upload.

    Returns:
        StepResult with output = YouTube video URL (or MP4 path in dry-run).
    """
    # --- MP4 conversion ---
    try:
        mp4_path, convert_msg = _create_mp4(episode_dir, research)
    except RuntimeError as exc:
        return StepResult(output=None, passed=False, message=str(exc), attempt=1)

    passed, validate_msg = _validate_mp4(mp4_path)
    if not passed:
        return StepResult(output=None, passed=False, message=validate_msg, attempt=1)

    print(f"  {convert_msg}")

    if dry_run:
        return StepResult(
            output=str(mp4_path),
            passed=True,
            message=f"Dry-run: {validate_msg} (upload skipped)",
            attempt=1,
        )

    # --- YouTube upload ---
    title = _build_title(topic, season, episode)
    description = _build_description(topic, research)
    tags = _build_tags(topic, research)

    print(f"  Title: {title}")
    print(f"  Privacy: {YOUTUBE_DEFAULT_PRIVACY}")

    try:
        video_url = _upload_to_youtube(
            mp4_path=mp4_path,
            title=title,
            description=description,
            tags=tags,
        )
    except RuntimeError as exc:
        return StepResult(output=str(mp4_path), passed=False, message=str(exc), attempt=1)
    except Exception as exc:  # noqa: BLE001
        return StepResult(
            output=str(mp4_path),
            passed=False,
            message=f"YouTube API error: {exc}",
            attempt=1,
        )

    return StepResult(
        output=video_url,
        passed=True,
        message=f"Uploaded: {video_url}",
        attempt=1,
    )
