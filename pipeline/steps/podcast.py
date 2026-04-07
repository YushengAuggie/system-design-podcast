"""Step 7: Podcast RSS Feed — upload MP3 to GitHub Releases and update RSS feed."""

import json
import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

from pydub import AudioSegment

from pipeline.config import (
    PODCAST_AUTHOR,
    PODCAST_DESCRIPTION,
    PODCAST_FEED_FILE,
    PODCAST_GITHUB_REPO,
    PODCAST_IMAGE_URL,
    PODCAST_TITLE,
    PODCAST_WEBSITE,
)
from pipeline.quality import StepResult

# iTunes XML namespace
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM_NS = "http://www.w3.org/2005/Atom"


def _format_duration(duration_ms: int) -> str:
    """Format milliseconds to HH:MM:SS string for iTunes duration."""
    total_sec = duration_ms // 1000
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    seconds = total_sec % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _get_mp3_duration_ms(mp3_path: Path) -> int:
    """Return duration of MP3 in milliseconds using pydub."""
    audio = AudioSegment.from_mp3(str(mp3_path))
    return len(audio)


def _upload_to_github_release(
    mp3_path: Path,
    season: int,
    episode: int,
    title: str,
) -> str:
    """Upload MP3 to a GitHub Release and return the download URL.

    Creates a new release tagged `ep-{season}-{episode}`, or uploads to the
    existing release if the tag already exists.

    Returns:
        Direct download URL for the MP3 asset.
    """
    tag = f"ep-{season}-{episode}"
    asset_name = mp3_path.name

    # Check if release already exists
    check_result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", PODCAST_GITHUB_REPO, "--json", "tagName"],
        capture_output=True,
        text=True,
    )

    if check_result.returncode == 0:
        # Release exists — upload asset to existing release
        print(f"  Release {tag} already exists. Uploading asset to existing release...")
        upload_result = subprocess.run(
            [
                "gh", "release", "upload", tag,
                str(mp3_path),
                "--repo", PODCAST_GITHUB_REPO,
                "--clobber",  # overwrite if asset already exists
            ],
            capture_output=True,
            text=True,
        )
        if upload_result.returncode != 0:
            raise RuntimeError(
                f"gh release upload failed: {upload_result.stderr.strip()}"
            )
    else:
        # Create a new release with the MP3
        print(f"  Creating release {tag} and uploading MP3...")
        create_result = subprocess.run(
            [
                "gh", "release", "create", tag,
                str(mp3_path),
                "--repo", PODCAST_GITHUB_REPO,
                "--title", f"Episode S{season:02d}E{episode:02d}: {title}",
                "--notes", f"Automated release for {PODCAST_TITLE} Season {season}, Episode {episode}: {title}",
            ],
            capture_output=True,
            text=True,
        )
        if create_result.returncode != 0:
            raise RuntimeError(
                f"gh release create failed: {create_result.stderr.strip()}"
            )

    # Retrieve the asset download URL from the release
    view_result = subprocess.run(
        [
            "gh", "release", "view", tag,
            "--repo", PODCAST_GITHUB_REPO,
            "--json", "assets",
        ],
        capture_output=True,
        text=True,
    )
    if view_result.returncode != 0:
        raise RuntimeError(
            f"Failed to retrieve release assets: {view_result.stderr.strip()}"
        )

    assets = json.loads(view_result.stdout).get("assets", [])
    for asset in assets:
        if asset.get("name") == asset_name:
            return asset["url"]

    # Fallback: construct the expected GitHub release asset URL
    return (
        f"https://github.com/{PODCAST_GITHUB_REPO}/releases/download/{tag}/{asset_name}"
    )


def _make_feed_skeleton() -> ET.Element:
    """Create a fresh RSS 2.0 feed element with iTunes namespace declarations."""
    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("atom", ATOM_NS)

    rss = ET.Element("rss")
    rss.set("version", "2.0")

    channel = ET.SubElement(rss, "channel")

    _sub(channel, "title", PODCAST_TITLE)
    _sub(channel, "link", PODCAST_WEBSITE)
    _sub(channel, "description", PODCAST_DESCRIPTION)
    _sub(channel, "language", "en")
    _sub(channel, "copyright", f"© {datetime.now(tz=timezone.utc).year} {PODCAST_AUTHOR}")
    _sub(channel, "lastBuildDate", format_datetime(datetime.now(tz=timezone.utc)))
    _sub(channel, "generator", "system-design-podcast pipeline")

    # atom:link for feed self-reference
    atom_link = ET.SubElement(channel, f"{{{ATOM_NS}}}link")
    atom_link.set("href", f"{PODCAST_WEBSITE}/feed.xml")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    # iTunes channel tags
    _sub(channel, f"{{{ITUNES_NS}}}author", PODCAST_AUTHOR)
    _sub(channel, f"{{{ITUNES_NS}}}subtitle", PODCAST_DESCRIPTION)
    _sub(channel, f"{{{ITUNES_NS}}}summary", PODCAST_DESCRIPTION)
    _sub(channel, f"{{{ITUNES_NS}}}explicit", "no")

    owner = ET.SubElement(channel, f"{{{ITUNES_NS}}}owner")
    _sub(owner, f"{{{ITUNES_NS}}}name", PODCAST_AUTHOR)

    image = ET.SubElement(channel, f"{{{ITUNES_NS}}}image")
    image.set("href", PODCAST_IMAGE_URL)

    return rss


def _sub(parent: ET.Element, tag: str, text: str) -> ET.Element:
    """Create a child element with text content."""
    el = ET.SubElement(parent, tag)
    el.text = text
    return el


def _build_episode_item(
    title: str,
    description: str,
    mp3_url: str,
    mp3_size: int,
    duration_ms: int,
    pub_date: datetime,
    season: int,
    episode: int,
) -> ET.Element:
    """Build a single <item> element for an episode."""
    item = ET.Element("item")

    _sub(item, "title", title)
    _sub(item, "link", f"{PODCAST_WEBSITE}/episodes/s{season:02d}e{episode:02d}")
    _sub(item, "description", description)
    _sub(item, "pubDate", format_datetime(pub_date))
    _sub(item, "guid", f"{PODCAST_WEBSITE}/episodes/s{season:02d}e{episode:02d}")

    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", mp3_url)
    enclosure.set("type", "audio/mpeg")
    enclosure.set("length", str(mp3_size))

    duration_str = _format_duration(duration_ms)
    _sub(item, f"{{{ITUNES_NS}}}duration", duration_str)
    _sub(item, f"{{{ITUNES_NS}}}episode", str(episode))
    _sub(item, f"{{{ITUNES_NS}}}season", str(season))
    _sub(item, f"{{{ITUNES_NS}}}summary", description)
    _sub(item, f"{{{ITUNES_NS}}}explicit", "no")

    image = ET.SubElement(item, f"{{{ITUNES_NS}}}image")
    image.set("href", PODCAST_IMAGE_URL)

    return item


def _parse_pub_date(item: ET.Element) -> datetime:
    """Parse pubDate from an existing <item> element, falling back to epoch."""
    from email.utils import parsedate_to_datetime

    pub_date_el = item.find("pubDate")
    if pub_date_el is not None and pub_date_el.text:
        try:
            return parsedate_to_datetime(pub_date_el.text)
        except Exception:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _load_or_create_feed(feed_path: Path) -> tuple[ET.Element, ET.Element]:
    """Load existing feed.xml or create a fresh skeleton.

    Returns:
        Tuple of (rss_root, channel_element).
    """
    if feed_path.exists():
        ET.register_namespace("itunes", ITUNES_NS)
        ET.register_namespace("atom", ATOM_NS)
        tree = ET.parse(str(feed_path))
        rss = tree.getroot()
        channel = rss.find("channel")
        if channel is None:
            raise ValueError("Existing feed.xml has no <channel> element")
        return rss, channel

    rss = _make_feed_skeleton()
    channel = rss.find("channel")
    assert channel is not None  # always present after _make_feed_skeleton
    return rss, channel


def _save_feed(rss: ET.Element, feed_path: Path) -> None:
    """Serialize the RSS tree to feed_path with XML declaration."""
    ET.indent(rss, space="  ")
    tree = ET.ElementTree(rss)
    tree.write(
        str(feed_path),
        encoding="UTF-8",
        xml_declaration=True,
    )


def update_rss_feed(
    feed_path: Path,
    title: str,
    description: str,
    mp3_url: str,
    mp3_size: int,
    duration_ms: int,
    pub_date: datetime,
    season: int,
    episode: int,
) -> None:
    """Load (or create) feed.xml, add the new episode, sort by pubDate descending."""
    rss, channel = _load_or_create_feed(feed_path)

    # Build the new episode item
    new_item = _build_episode_item(
        title=title,
        description=description,
        mp3_url=mp3_url,
        mp3_size=mp3_size,
        duration_ms=duration_ms,
        pub_date=pub_date,
        season=season,
        episode=episode,
    )

    # Collect existing items, removing them from channel
    existing_items = channel.findall("item")
    for item in existing_items:
        channel.remove(item)

    # Add new item to the pool and sort descending by pubDate
    all_items = existing_items + [new_item]
    all_items.sort(key=_parse_pub_date, reverse=True)

    # Update lastBuildDate
    last_build_el = channel.find("lastBuildDate")
    if last_build_el is not None:
        last_build_el.text = format_datetime(datetime.now(tz=timezone.utc))

    # Re-append all items in sorted order
    for item in all_items:
        channel.append(item)

    _save_feed(rss, feed_path)


def _validate_feed(feed_path: Path) -> tuple[bool, str]:
    """Quality gate: feed.xml must exist and be valid XML."""
    if not feed_path.exists():
        return False, f"feed.xml not found at {feed_path}"
    try:
        tree = ET.parse(str(feed_path))
        root = tree.getroot()
        channel = root.find("channel")
        if channel is None:
            return False, "feed.xml missing <channel> element"
        items = channel.findall("item")
        return True, f"Valid RSS feed with {len(items)} episode(s)"
    except ET.ParseError as exc:
        return False, f"Invalid XML in feed.xml: {exc}"


def run_podcast(
    episode_dir: Path,
    topic: str,
    season: int,
    episode: int,
    research_data: dict,
    dry_run: bool = False,
) -> StepResult:
    """Execute the podcast RSS step.

    Steps:
    1. Locate the generated MP3 in episode_dir.
    2. Upload MP3 to GitHub Release (skip in dry-run).
    3. Read duration and file size.
    4. Update feed.xml in the repo root.

    Quality gate: feed.xml exists and is valid XML.
    """
    mp3_path = episode_dir / "episode.mp3"
    if not mp3_path.exists():
        return StepResult(
            output=None,
            passed=False,
            message=f"MP3 not found: {mp3_path}",
            attempt=1,
        )

    # Episode title and description
    ep_title = f"S{season:02d}E{episode:02d}: {topic}"
    summary = research_data.get("summary", f"A system design deep-dive on {topic}.")
    ep_description = f"{summary}\n\nSeason {season}, Episode {episode} of {PODCAST_TITLE}."

    # Locate feed.xml relative to repo root (two levels up from pipeline/steps/)
    # The repo root is the parent of the pipeline package dir, which is CWD when invoked.
    repo_root = Path.cwd()
    feed_path = repo_root / PODCAST_FEED_FILE

    # Collect audio metadata
    duration_ms = _get_mp3_duration_ms(mp3_path)
    mp3_size = os.path.getsize(mp3_path)
    pub_date = datetime.now(tz=timezone.utc)

    if dry_run:
        # Dry-run: use placeholder URL, still generate the feed
        mp3_url = f"https://github.com/{PODCAST_GITHUB_REPO}/releases/download/ep-{season}-{episode}/{mp3_path.name}"
        print(f"  [dry-run] Skipping GitHub Release upload. Placeholder URL: {mp3_url}")
    else:
        # Upload to GitHub Releases and get real URL
        print(f"  Uploading {mp3_path.name} to GitHub Release ep-{season}-{episode}...")
        mp3_url = _upload_to_github_release(mp3_path, season, episode, topic)
        print(f"  Upload complete. Asset URL: {mp3_url}")

    # Update the RSS feed
    print(f"  Updating RSS feed at {feed_path}...")
    update_rss_feed(
        feed_path=feed_path,
        title=ep_title,
        description=ep_description,
        mp3_url=mp3_url,
        mp3_size=mp3_size,
        duration_ms=duration_ms,
        pub_date=pub_date,
        season=season,
        episode=episode,
    )

    passed, message = _validate_feed(feed_path)
    return StepResult(
        output=str(feed_path),
        passed=passed,
        message=message,
        attempt=1,
    )
