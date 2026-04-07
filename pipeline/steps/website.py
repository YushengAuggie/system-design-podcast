"""Step 7: Website Generation — build static HTML pages from episode outputs."""

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

from pipeline.config import EPISODES_DIR, WEBSITE_DIR, WEBSITE_URL
from pipeline.quality import StepResult
from pipeline.utils import slugify


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_optional_json(path: Path) -> dict:
    """Load JSON file if it exists, else return empty dict."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _load_optional_text(path: Path) -> str:
    """Load text file if it exists, else return empty string."""
    if path.exists():
        return path.read_text()
    return ""


def _mermaid_to_svg(mmd_path: Path, svg_path: Path) -> bool:
    """Convert a Mermaid .mmd file to SVG using mmdc if available.

    Returns True on success, False if mmdc is unavailable or fails.
    """
    mmdc = shutil.which("mmdc")
    if not mmdc:
        return False
    try:
        result = subprocess.run(
            [mmdc, "-i", str(mmd_path), "-o", str(svg_path), "-b", "transparent"],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0 and svg_path.exists()
    except Exception:
        return False


def _extract_episode_info(ep_dir: Path) -> dict:
    """Extract season/episode number and topic slug from a directory name.

    Directory naming convention: ``NN-slug`` (e.g. ``01-url-shortener``).
    """
    name = ep_dir.name
    match = re.match(r"^(\d+)-(.+)$", name)
    episode_num = int(match.group(1)) if match else 0
    slug = match.group(2) if match else name

    # Research file can override/supplement
    research = _load_optional_json(ep_dir / "research.json")
    season = int(research.get("season", 1))
    # Episode number from research takes priority if present
    if research.get("episode"):
        episode_num = int(research["episode"])
    topic = research.get("topic", slug.replace("-", " ").title())

    return {
        "dir": ep_dir,
        "slug": slug,
        "season": season,
        "episode": episode_num,
        "topic": topic,
        "research": research,
    }


# ── Diagram HTML ──────────────────────────────────────────────────────────────


def _render_diagram_html(ep_dir: Path, ep_out_dir: Path) -> str:
    """Convert diagram.mmd → SVG (if mmdc available) and return HTML fragment."""
    mmd_path = ep_dir / "diagram.mmd"
    if not mmd_path.exists():
        return '<div class="mermaid-placeholder">Architecture diagram coming soon.</div>'

    svg_path = ep_out_dir / "diagram.svg"
    success = _mermaid_to_svg(mmd_path, svg_path)

    if success:
        return '<img src="diagram.svg" alt="Architecture diagram" loading="lazy" />'

    # Fallback: embed raw Mermaid source as a code block
    mmd_source = html.escape(mmd_path.read_text().strip())
    return (
        '<div class="mermaid-placeholder">'
        '<p style="margin-bottom:12px;">Architecture diagram (install <code>mmdc</code> to render automatically)</p>'
        f'<pre style="text-align:left; font-size:0.75rem; overflow:auto; background:var(--cream); '
        f'padding:16px; border-radius:4px; color:var(--text); max-height:260px;">{mmd_source}</pre>'
        "</div>"
    )


# ── Transcript HTML ───────────────────────────────────────────────────────────


def _render_transcript_html(ep_dir: Path) -> str:
    """Convert script.md into styled HTML dialogue lines."""
    script = _load_optional_text(ep_dir / "script.md")
    if not script.strip():
        return "<p>Transcript not available.</p>"

    pattern = re.compile(r"\*\*\[Host ([AB])\]:\*\*\s*(.*)")
    lines = []
    for line in script.split("\n"):
        stripped = line.strip()
        match = pattern.match(stripped)
        if match:
            speaker = match.group(1)
            text = html.escape(match.group(2).strip())
            label = "Alex" if speaker == "A" else "Blake"
            css_class = "host-a" if speaker == "A" else "host-b"
            lines.append(
                f'<p class="host-line {css_class}">'
                f'<span class="host-label">{label}</span> {text}</p>'
            )
        elif stripped.startswith("##") or stripped.startswith("---"):
            # Segment headers / dividers
            if stripped.startswith("##"):
                heading = html.escape(stripped.lstrip("#").strip())
                lines.append(
                    f'<h3 style="font-size:0.85rem; font-weight:700; text-transform:uppercase; '
                    f'letter-spacing:0.06em; color:var(--warm-brown); margin:20px 0 10px;">'
                    f"{heading}</h3>"
                )
            else:
                lines.append('<hr style="border:none; border-top:1px solid var(--light-tan); margin:16px 0;" />')
    return "\n".join(lines) if lines else "<p>Transcript not available.</p>"


# ── References HTML ───────────────────────────────────────────────────────────


def _render_references_html(research: dict) -> str:
    """Render references list from research data."""
    refs = research.get("real_world_references", [])
    if not refs:
        return '<li><span class="ref-detail">No references available.</span></li>'

    items = []
    for ref in refs:
        company = html.escape(ref.get("company", ""))
        detail = html.escape(ref.get("detail", ""))
        url = ref.get("url", "")
        url_esc = html.escape(url)
        url_text = html.escape(url[:60] + ("…" if len(url) > 60 else ""))
        items.append(
            f"<li>"
            f'<span class="ref-company">{company}</span>'
            f'<span class="ref-detail">{detail}</span>'
            + (f'<a href="{url_esc}" target="_blank" rel="noopener">{url_text}</a>' if url else "")
            + "</li>"
        )
    return "\n".join(items)


# ── Episode Page ──────────────────────────────────────────────────────────────


def _render_episode_page(info: dict, website_dir: Path, template: str) -> Path:
    """Render a single episode HTML page and return its output path."""
    ep_dir: Path = info["dir"]
    slug: str = info["slug"]

    # Output dir: website/<slug>/
    ep_out_dir = website_dir / slug
    ep_out_dir.mkdir(parents=True, exist_ok=True)

    # Copy audio if present
    audio_src = ep_dir / "episode.mp3"
    if audio_src.exists():
        shutil.copy2(audio_src, ep_out_dir / "episode.mp3")

    # Build substitution values
    season = info["season"]
    episode = info["episode"]
    topic = info["topic"]
    research = info["research"]
    summary = research.get("summary", f"A 10-minute deep dive into {topic}.")

    diagram_html = _render_diagram_html(ep_dir, ep_out_dir)
    transcript_html = _render_transcript_html(ep_dir)
    references_html = _render_references_html(research)

    page = template
    page = page.replace("{{EPISODE_TITLE}}", html.escape(topic))
    page = page.replace("{{EPISODE_SUMMARY}}", html.escape(summary))
    page = page.replace("{{EPISODE_SLUG}}", slug)
    page = page.replace("{{SEASON}}", str(season))
    page = page.replace("{{EPISODE}}", str(episode))
    page = page.replace("{{DIAGRAM_CONTENT}}", diagram_html)
    page = page.replace("{{TRANSCRIPT_CONTENT}}", transcript_html)
    page = page.replace("{{REFERENCES_CONTENT}}", references_html)

    out_path = ep_out_dir / "index.html"
    out_path.write_text(page)
    return out_path


# ── Episode Card HTML ─────────────────────────────────────────────────────────


def _render_episode_card(info: dict, website_dir: Path) -> str:
    """Return the HTML snippet for one episode card on the index page."""
    slug = info["slug"]
    season = info["season"]
    episode_num = info["episode"]
    topic = html.escape(info["topic"])
    research = info["research"]
    summary = html.escape(research.get("summary", f"A deep dive into {info['topic']}."))

    ep_out_dir = website_dir / slug
    has_audio = (ep_out_dir / "episode.mp3").exists()
    has_diagram = (ep_out_dir / "diagram.svg").exists()

    if has_diagram:
        thumbnail = f'<img src="{slug}/diagram.svg" alt="{topic} architecture diagram" loading="lazy" />'
    else:
        thumbnail = '<div class="card-diagram-placeholder">🏗️<span>Diagram</span></div>'

    audio_html = ""
    if has_audio:
        audio_html = (
            '<div class="card-audio">'
            f'<audio controls preload="none"><source src="{slug}/episode.mp3" type="audio/mpeg" /></audio>'
            "</div>"
        )

    card = f"""      <article class="episode-card">
        <a href="{slug}/index.html">
          <div class="card-diagram">{thumbnail}</div>
        </a>
        <div class="card-body">
          <div class="card-meta">
            <span class="badge badge-season">S{season}</span>
            <span class="badge badge-episode">E{episode_num:02d}</span>
          </div>
          <h3 class="card-title"><a href="{slug}/index.html">{topic}</a></h3>
          <p class="card-description">{summary}</p>
          {audio_html}
        </div>
        <div class="card-footer">
          <a href="{slug}/index.html">Listen &amp; read →</a>
        </div>
      </article>"""
    return card


# ── Index Update ──────────────────────────────────────────────────────────────


def _update_index(index_path: Path, episode_cards_html: str) -> None:
    """Replace the episode listing region in index.html."""
    content = index_path.read_text()
    start_marker = "<!-- EPISODES_START -->"
    end_marker = "<!-- EPISODES_END -->"

    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx == -1 or end_idx == -1:
        # Markers not found — append a warning comment
        return

    new_content = (
        content[: start_idx + len(start_marker)]
        + "\n"
        + episode_cards_html
        + "\n"
        + content[end_idx:]
    )
    index_path.write_text(new_content)


# ── Mock Data ─────────────────────────────────────────────────────────────────


def _mock_episode_infos() -> list[dict]:
    """Return fake episode infos for dry-run mode."""
    topics = [
        ("url-shortener", 1, 1, "URL Shortener", "Design a scalable URL shortener like bit.ly — covering hashing, redirects, and analytics at scale."),
        ("rate-limiter", 1, 2, "Rate Limiter", "Build a distributed rate limiter using token buckets, sliding windows, and Redis counters."),
        ("distributed-cache", 1, 3, "Distributed Cache", "Cache invalidation, eviction policies, and consistent hashing in a system like Memcached or Redis."),
    ]
    infos = []
    for slug, season, episode, topic, summary in topics:
        infos.append({
            "dir": Path(EPISODES_DIR) / f"{episode:02d}-{slug}",
            "slug": f"{episode:02d}-{slug}",
            "season": season,
            "episode": episode,
            "topic": topic,
            "research": {
                "topic": topic,
                "season": season,
                "episode": episode,
                "summary": summary,
                "real_world_references": [
                    {"company": "Google", "detail": f"Google's {topic} approach", "url": "https://research.google/"},
                    {"company": "Netflix", "detail": f"Netflix {topic} at scale", "url": "https://netflixtechblog.com/"},
                ],
            },
        })
    return infos


# ── Main Step ─────────────────────────────────────────────────────────────────


def run_website(dry_run: bool = False) -> StepResult:
    """Build or update the static website from all episode directories.

    Reads all episode directories under EPISODES_DIR, generates/updates
    individual episode pages and the main index.html.

    Returns:
        StepResult with output=website_dir, passed=True on success.
    """
    base_dir = Path(".")
    website_dir = base_dir / WEBSITE_DIR
    episodes_base = base_dir / EPISODES_DIR

    website_dir.mkdir(parents=True, exist_ok=True)

    # Load HTML template
    template_path = website_dir / "episode-template.html"
    if not template_path.exists():
        return StepResult(
            output=None,
            passed=False,
            message=f"Episode template not found at {template_path}",
            attempt=1,
        )
    template = template_path.read_text()

    # Load index.html
    index_path = website_dir / "index.html"
    if not index_path.exists():
        return StepResult(
            output=None,
            passed=False,
            message=f"index.html not found at {index_path}",
            attempt=1,
        )

    # Collect episode infos
    if dry_run:
        episode_infos = _mock_episode_infos()
        print("  Dry-run: using mock episode data")
    else:
        episode_infos = []
        if episodes_base.exists():
            for ep_dir in sorted(episodes_base.iterdir()):
                if ep_dir.is_dir() and not ep_dir.name.startswith("."):
                    episode_infos.append(_extract_episode_info(ep_dir))
        print(f"  Found {len(episode_infos)} episode(s) in {episodes_base}/")

    if not episode_infos:
        # Nothing to generate — leave index as-is (shows empty state)
        return StepResult(
            output=str(website_dir),
            passed=True,
            message="No episodes found — website left with empty state",
            attempt=1,
        )

    # Sort: season asc, episode asc
    episode_infos.sort(key=lambda e: (e["season"], e["episode"]))

    # Render individual episode pages
    rendered = 0
    for info in episode_infos:
        out_path = _render_episode_page(info, website_dir, template)
        print(f"  Generated episode page: {out_path}")
        rendered += 1

    # Build episode cards HTML
    cards_html = "\n".join(_render_episode_card(info, website_dir) for info in episode_infos)

    # Update index.html
    _update_index(index_path, cards_html)
    print(f"  Updated index.html with {rendered} episode card(s)")

    return StepResult(
        output=str(website_dir),
        passed=True,
        message=f"Generated website with {rendered} episode(s) → {website_dir}/",
        attempt=1,
    )
