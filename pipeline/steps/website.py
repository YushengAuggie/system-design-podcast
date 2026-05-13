"""Step 7: Website Generation — build static HTML pages from episode outputs."""

from __future__ import annotations


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
    """Render diagram section: prefer interactive HTML, fall back to SVG/Mermaid."""
    # Priority 1: Interactive diagram HTML
    diagram_html_path = ep_dir / "diagram.html"
    if diagram_html_path.exists():
        # Copy diagram.html to output dir
        shutil.copy2(diagram_html_path, ep_out_dir / "diagram.html")
        # Also copy diagram.png as fallback image if available
        diagram_png = ep_dir / "diagram.png"
        if diagram_png.exists():
            shutil.copy2(diagram_png, ep_out_dir / "diagram.png")
        return (
            '<div class="diagram-header">'
            '<h2>\U0001f3d7 Architecture Diagram</h2>'
            '<a href="diagram.html" target="_blank" rel="noopener" class="diagram-fullscreen-link">\u2197 Open full screen</a>'
            '</div>'
            '<iframe src="diagram.html" '
            'style="width:100%; height:700px; border:none; border-radius:8px;" '
            'loading="lazy" title="Interactive Architecture Diagram"></iframe>'
        )

    # Priority 2: SVG from Mermaid
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


# ── Article / Study Guide HTML ────────────────────────────────────────────────


def _render_article_html(ep_dir: Path, filename: str = "article.md") -> str:
    """Convert article.md into styled HTML for the study guide section."""
    article_md = _load_optional_text(ep_dir / filename)
    if not article_md.strip():
        return '<p style="color:var(--text-dim); font-size:0.9rem;">Study guide coming soon.</p>'

    lines = article_md.split("\n")
    html_parts: list[str] = []
    in_table = False
    in_blockquote = False
    in_list = False
    list_type = ""  # "ol" or "ul"

    def _close_list():
        nonlocal in_list, list_type
        if in_list:
            html_parts.append(f"</{list_type}>")
            in_list = False
            list_type = ""

    def _close_blockquote():
        nonlocal in_blockquote
        if in_blockquote:
            html_parts.append("</blockquote>")
            in_blockquote = False

    def _inline_format(text: str) -> str:
        """Apply inline markdown formatting."""
        # Bold
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # Italic
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        # Inline code
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        # Links
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
        return text

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Table detection
        if stripped.startswith("|") and "|" in stripped[1:]:
            _close_list()
            _close_blockquote()
            if not in_table:
                html_parts.append("<table>")
                in_table = True
                # Header row
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                html_parts.append("<thead><tr>" + "".join(f"<th>{_inline_format(html.escape(c))}</th>" for c in cells) + "</tr></thead>")
                # Skip separator row
                if i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
                    i += 1
                html_parts.append("<tbody>")
            else:
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                html_parts.append("<tr>" + "".join(f"<td>{_inline_format(html.escape(c))}</td>" for c in cells) + "</tr>")
            i += 1
            continue
        elif in_table:
            html_parts.append("</tbody></table>")
            in_table = False

        # Empty line
        if not stripped:
            _close_list()
            _close_blockquote()
            i += 1
            continue

        # Headings
        if stripped.startswith("# ") and not stripped.startswith("## "):
            _close_list()
            _close_blockquote()
            heading_text = html.escape(stripped[2:])
            html_parts.append(f"<h2>{_inline_format(heading_text)}</h2>")
            i += 1
            continue

        if stripped.startswith("## "):
            _close_list()
            _close_blockquote()
            heading_text = html.escape(stripped[3:])
            html_parts.append(f"<h2>{_inline_format(heading_text)}</h2>")
            i += 1
            continue

        # Blockquote
        if stripped.startswith("> "):
            _close_list()
            if not in_blockquote:
                html_parts.append("<blockquote>")
                in_blockquote = True
            quote_text = html.escape(stripped[2:])
            html_parts.append(f"<p>{_inline_format(quote_text)}</p>")
            i += 1
            continue

        # Ordered list
        ol_match = re.match(r"^(\d+)\.\s+(.+)", stripped)
        if ol_match:
            _close_blockquote()
            if not in_list or list_type != "ol":
                _close_list()
                html_parts.append("<ol>")
                in_list = True
                list_type = "ol"
            item_text = html.escape(ol_match.group(2))
            html_parts.append(f"<li>{_inline_format(item_text)}</li>")
            i += 1
            continue

        # Unordered list
        if stripped.startswith("- ") or stripped.startswith("* "):
            _close_blockquote()
            if not in_list or list_type != "ul":
                _close_list()
                html_parts.append("<ul>")
                in_list = True
                list_type = "ul"
            item_text = html.escape(stripped[2:])
            html_parts.append(f"<li>{_inline_format(item_text)}</li>")
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^-{3,}$", stripped) or re.match(r"^\*{3,}$", stripped):
            _close_list()
            _close_blockquote()
            html_parts.append("<hr />")
            i += 1
            continue

        # Regular paragraph
        _close_list()
        _close_blockquote()
        para_text = html.escape(stripped)
        html_parts.append(f"<p>{_inline_format(para_text)}</p>")
        i += 1

    # Close any open elements
    if in_table:
        html_parts.append("</tbody></table>")
    _close_list()
    _close_blockquote()

    return "\n".join(html_parts)


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


def _get_audio_url_relative(slug: str) -> str:
    """Get relative audio URL for main index page."""
    return f"{slug}/episode.mp3"


def _get_audio_url_episode() -> str:
    """Get audio URL for episode page (same directory)."""
    return "episode.mp3"


def _build_listen_links(ep_dir: Path) -> str:
    """Build listen-on links from available data."""
    links = []
    youtube_path = ep_dir / "youtube.json"
    if youtube_path.exists():
        try:
            yt_data = json.loads(youtube_path.read_text())
            video_id = yt_data.get("video_id", "")
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
                links.append(
                    f'<a href="{url}" class="listen-btn" target="_blank" rel="noopener">▶ YouTube</a>'
                )
        except Exception:
            pass
    if not links:
        return '<span style="font-size:0.8rem; color:var(--text-light);">More platforms coming soon</span>'
    return '\n          '.join(links)


def _render_episode_page(info: dict, website_dir: Path, template: str) -> Path:
    """Render a single episode HTML page and return its output path."""
    ep_dir: Path = info["dir"]
    slug: str = info["slug"]

    # Output dir: website/<slug>/
    ep_out_dir = website_dir / slug
    ep_out_dir.mkdir(parents=True, exist_ok=True)

    # Build substitution values
    season = info["season"]
    episode = info["episode"]
    topic = info["topic"]
    research = info["research"]
    summary = research.get("summary", f"A 10-minute deep dive into {topic}.")

    # Audio: use GitHub Release URL (mp3 is in .gitignore)
    # Copy audio to website dir (force-included in git via !docs/**/*.mp3)
    audio_src = ep_dir / "episode.mp3"
    if audio_src.exists():
        shutil.copy2(audio_src, ep_out_dir / "episode.mp3")

    audio_url = _get_audio_url_episode()

    # YouTube link if available
    listen_links = _build_listen_links(ep_dir)

    diagram_html = _render_diagram_html(ep_dir, ep_out_dir)
    article_html = _render_article_html(ep_dir)
    article_html_zh = _render_article_html(ep_dir, filename="article_zh.md")
    transcript_html = _render_transcript_html(ep_dir)
    references_html = _render_references_html(research)

    page = template
    page = page.replace("{{EPISODE_TITLE}}", html.escape(topic))
    page = page.replace("{{EPISODE_SUMMARY}}", html.escape(summary))
    page = page.replace("{{EPISODE_SLUG}}", slug)
    page = page.replace("{{SEASON}}", str(season))
    page = page.replace("{{EPISODE}}", str(episode))
    page = page.replace("{{AUDIO_URL}}", audio_url)
    page = page.replace("{{LISTEN_LINKS}}", listen_links)
    page = page.replace("{{ARTICLE_CONTENT}}", article_html)
    page = page.replace("{{ARTICLE_CONTENT_ZH}}", article_html_zh)
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
    ep_dir = info["dir"]
    has_diagram_png = (ep_out_dir / "diagram.png").exists()
    has_diagram_svg = (ep_out_dir / "diagram.svg").exists()

    if has_diagram_png:
        thumbnail = f'<img src="{slug}/diagram.png" alt="{topic} architecture diagram" loading="lazy" />'
    elif has_diagram_svg:
        thumbnail = f'<img src="{slug}/diagram.svg" alt="{topic} architecture diagram" loading="lazy" />'
    else:
        thumbnail = '<div class="card-diagram-placeholder">🏗️<span>Diagram</span></div>'

    card_audio_url = _get_audio_url_relative(slug)
    audio_html = (
        '<div class="card-audio">'
        f'<audio controls preload="none"><source src="{card_audio_url}" type="audio/mpeg" /></audio>'
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
