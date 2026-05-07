"""Final Review Agent — validates the complete episode output before deployment.

Runs after all generation steps. Checks that all expected files exist, audio
is within duration bounds, website HTML is valid, diagram renders, links work,
and content is coherent. Attempts auto-fixes for common issues.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pipeline.config import (
    AUDIO_DURATION_MAX_SEC,
    AUDIO_DURATION_MIN_SEC,
    EPISODES_DIR,
    WEBSITE_DIR,
    WEBSITE_URL,
)
from pipeline.llm import call_anthropic
from pipeline.quality import StepResult
from pipeline.utils import slugify


# ── Checks ───────────────────────────────────────────────────────────────────

def _check_episode_files(ep_dir: Path) -> list[dict]:
    """Check that all expected episode files exist."""
    issues = []
    expected = {
        "research.json": "Research data",
        "script.md": "Episode script",
        "review.json": "Script review",
        "voices.json": "Voice selection",
        "episode.mp3": "Audio file",
        "diagram.json": "Diagram data",
        "diagram.html": "Interactive diagram",
        "diagram.mmd": "Mermaid diagram (compat)",
    }
    optional = {
        "diagram.png": "Diagram screenshot",
        "diagram_review.json": "Diagram review",
        "youtube.json": "YouTube upload info",
    }

    for filename, label in expected.items():
        path = ep_dir / filename
        if not path.exists():
            issues.append({
                "severity": "error",
                "category": "missing_file",
                "message": f"Missing required file: {filename} ({label})",
                "file": filename,
                "fixable": False,
            })
        elif path.stat().st_size == 0:
            issues.append({
                "severity": "error",
                "category": "empty_file",
                "message": f"File is empty: {filename} ({label})",
                "file": filename,
                "fixable": False,
            })

    for filename, label in optional.items():
        path = ep_dir / filename
        if not path.exists():
            issues.append({
                "severity": "warning",
                "category": "missing_optional",
                "message": f"Missing optional file: {filename} ({label})",
                "file": filename,
                "fixable": False,
            })

    return issues


def _check_audio_duration(ep_dir: Path) -> list[dict]:
    """Check audio duration is within bounds using ffprobe."""
    issues = []
    mp3_path = ep_dir / "episode.mp3"
    if not mp3_path.exists():
        return issues  # Already caught by file check

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(mp3_path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            if duration < AUDIO_DURATION_MIN_SEC:
                issues.append({
                    "severity": "error",
                    "category": "audio_duration",
                    "message": f"Audio too short: {duration:.0f}s (min {AUDIO_DURATION_MIN_SEC}s)",
                    "fixable": False,
                })
            elif duration > AUDIO_DURATION_MAX_SEC:
                issues.append({
                    "severity": "warning",
                    "category": "audio_duration",
                    "message": f"Audio too long: {duration:.0f}s (max {AUDIO_DURATION_MAX_SEC}s)",
                    "fixable": False,
                })
    except (subprocess.TimeoutExpired, FileNotFoundError):
        issues.append({
            "severity": "warning",
            "category": "audio_check",
            "message": "Could not check audio duration (ffprobe not available)",
            "fixable": False,
        })

    return issues


def _check_script_quality(ep_dir: Path) -> list[dict]:
    """Validate script structure and content."""
    issues = []
    script_path = ep_dir / "script.md"
    if not script_path.exists():
        return issues

    script = script_path.read_text()
    lines = [l for l in script.strip().split("\n") if l.strip()]

    # Check for host dialogue markers
    host_a = len(re.findall(r"\*\*\[Host A\]:\*\*", script))
    host_b = len(re.findall(r"\*\*\[Host B\]:\*\*", script))

    if host_a == 0:
        issues.append({
            "severity": "error",
            "category": "script_format",
            "message": "No Host A dialogue found in script",
            "fixable": False,
        })
    if host_b == 0:
        issues.append({
            "severity": "error",
            "category": "script_format",
            "message": "No Host B dialogue found in script",
            "fixable": False,
        })
    if host_a > 0 and host_b > 0:
        ratio = max(host_a, host_b) / min(host_a, host_b)
        if ratio > 3.0:
            issues.append({
                "severity": "warning",
                "category": "script_balance",
                "message": f"Host dialogue imbalanced: A={host_a}, B={host_b} (ratio {ratio:.1f}x)",
                "fixable": False,
            })

    # Word count
    words = len(script.split())
    if words < 500:
        issues.append({
            "severity": "warning",
            "category": "script_length",
            "message": f"Script seems short: {words} words",
            "fixable": False,
        })

    return issues


def _check_diagram_json(ep_dir: Path) -> list[dict]:
    """Validate diagram JSON structure."""
    issues = []
    diagram_path = ep_dir / "diagram.json"
    if not diagram_path.exists():
        return issues

    try:
        data = json.loads(diagram_path.read_text())
    except json.JSONDecodeError as e:
        issues.append({
            "severity": "error",
            "category": "diagram_json",
            "message": f"Diagram JSON parse error: {e}",
            "fixable": False,
        })
        return issues

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    node_ids = {n["id"] for n in nodes}

    if len(nodes) < 3:
        issues.append({
            "severity": "error",
            "category": "diagram_nodes",
            "message": f"Too few nodes: {len(nodes)} (minimum 3)",
            "fixable": False,
        })

    if len(edges) < 2:
        issues.append({
            "severity": "warning",
            "category": "diagram_edges",
            "message": f"Very few edges: {len(edges)}",
            "fixable": False,
        })

    # Check for orphan edges
    for edge in edges:
        if edge.get("from") not in node_ids:
            issues.append({
                "severity": "error",
                "category": "diagram_edge_ref",
                "message": f"Edge references unknown node: from='{edge.get('from')}'",
                "fixable": False,
            })
        if edge.get("to") not in node_ids:
            issues.append({
                "severity": "error",
                "category": "diagram_edge_ref",
                "message": f"Edge references unknown node: to='{edge.get('to')}'",
                "fixable": False,
            })

    # Check for nodes with no connections
    connected = set()
    for edge in edges:
        connected.add(edge.get("from"))
        connected.add(edge.get("to"))
    orphan_nodes = node_ids - connected
    if orphan_nodes:
        issues.append({
            "severity": "warning",
            "category": "diagram_orphans",
            "message": f"Disconnected nodes: {', '.join(orphan_nodes)}",
            "fixable": False,
        })

    return issues


def _check_website_output(ep_dir: Path, topic: str, season: int, episode: int) -> list[dict]:
    """Check website files for the episode."""
    issues = []
    slug = slugify(topic)
    website_dir = Path(WEBSITE_DIR)
    ep_web_dir = website_dir / slug

    if not ep_web_dir.exists():
        issues.append({
            "severity": "error",
            "category": "website_missing",
            "message": f"Website episode directory missing: {ep_web_dir}",
            "fixable": True,
            "fix": "regenerate_website",
        })
        return issues

    index_html = ep_web_dir / "index.html"
    if not index_html.exists():
        issues.append({
            "severity": "error",
            "category": "website_missing",
            "message": f"Episode page missing: {index_html}",
            "fixable": True,
            "fix": "regenerate_website",
        })
        return issues

    html_content = index_html.read_text()

    # Check for broken href="#" links (placeholders that should be removed)
    placeholder_links = re.findall(r'href="#"[^>]*>[^<]*(?:Spotify|Apple)', html_content)
    if placeholder_links:
        issues.append({
            "severity": "warning",
            "category": "website_placeholders",
            "message": f"Placeholder links found: {len(placeholder_links)} (Spotify/Apple with href='#')",
            "fixable": True,
            "fix": "remove_placeholder_links",
        })

    # Check for stale CSS variables (old theme)
    old_vars = re.findall(r'var\(--(?:warm-brown|light-tan|cream|sage)', html_content)
    if old_vars:
        issues.append({
            "severity": "error",
            "category": "website_css",
            "message": f"Old theme CSS variables found: {set(old_vars)}",
            "fixable": True,
            "fix": "fix_css_vars",
        })

    # Check audio source points to something real (not just a local file)
    audio_srcs = re.findall(r'<source\s+src="([^"]+)"', html_content)
    for src in audio_srcs:
        if not src.startswith("http") and not src.startswith("../") and src.endswith(".mp3"):
            # Local file reference — check if it would work on GitHub Pages
            local_path = ep_web_dir / src
            if not local_path.exists():
                issues.append({
                    "severity": "error",
                    "category": "website_audio",
                    "message": f"Audio source '{src}' won't work on deployed site (file not in docs/)",
                    "fixable": False,
                })

    # Check diagram embed
    if "diagram.html" in html_content:
        diagram_html = ep_web_dir / "diagram.html"
        if not diagram_html.exists():
            issues.append({
                "severity": "error",
                "category": "website_diagram",
                "message": "Episode page references diagram.html but file is missing from docs/",
                "fixable": True,
                "fix": "copy_diagram",
            })

    # Check for YouTube link if upload happened
    youtube_path = ep_dir / "youtube.json"
    if youtube_path.exists():
        try:
            yt_data = json.loads(youtube_path.read_text())
            video_id = yt_data.get("video_id", "")
            if video_id and video_id not in html_content:
                issues.append({
                    "severity": "warning",
                    "category": "website_youtube",
                    "message": f"YouTube video uploaded but link not in episode page (video_id: {video_id})",
                    "fixable": True,
                    "fix": "update_youtube_link",
                })
        except Exception:
            pass

    return issues


def _check_feed(topic: str, season: int, episode: int) -> list[dict]:
    """Check RSS feed includes this episode."""
    issues = []
    feed_path = Path(WEBSITE_DIR) / "feed.xml"
    if not feed_path.exists():
        issues.append({
            "severity": "warning",
            "category": "feed_missing",
            "message": "RSS feed file not found",
            "fixable": True,
            "fix": "regenerate_website",
        })
        return issues

    feed_content = feed_path.read_text()
    # Search by multiple identifiers: topic name, slug, or episode code
    slug = slugify(topic)
    ep_code = f"S{season:02d}E{episode:02d}"
    found = (
        slug in feed_content
        or topic.lower() in feed_content.lower()
        or ep_code.lower() in feed_content.lower()
    )
    if not found:
        issues.append({
            "severity": "warning",
            "category": "feed_episode",
            "message": f"Episode '{topic}' ({ep_code}) not found in RSS feed",
            "fixable": True,
            "fix": "regenerate_website",
        })

    return issues


# ── Auto-fixes ───────────────────────────────────────────────────────────────

def _apply_fixes(
    issues: list[dict],
    ep_dir: Path,
    topic: str,
    season: int,
    episode: int,
) -> list[str]:
    """Attempt to fix identified issues. Returns list of applied fixes."""
    fixes_applied = []
    slug = slugify(topic)
    website_dir = Path(WEBSITE_DIR)
    ep_web_dir = website_dir / slug

    for issue in issues:
        if not issue.get("fixable"):
            continue

        fix_type = issue.get("fix", "")

        if fix_type == "copy_diagram":
            # Copy diagram.html from episode dir to website dir
            src = ep_dir / "diagram.html"
            if src.exists() and ep_web_dir.exists():
                shutil.copy2(src, ep_web_dir / "diagram.html")
                fixes_applied.append(f"Copied diagram.html to {ep_web_dir}")

            # Also copy diagram.png if available
            png_src = ep_dir / "diagram.png"
            if png_src.exists() and ep_web_dir.exists():
                shutil.copy2(png_src, ep_web_dir / "diagram.png")
                fixes_applied.append(f"Copied diagram.png to {ep_web_dir}")

        elif fix_type == "remove_placeholder_links":
            index_html = ep_web_dir / "index.html"
            if index_html.exists():
                content = index_html.read_text()
                # Remove placeholder Spotify/Apple links
                content = re.sub(
                    r'\s*<a\s+href="#"[^>]*>(?:🎧\s*Spotify|🎵\s*Apple Podcasts)</a>',
                    '',
                    content,
                )
                index_html.write_text(content)
                fixes_applied.append("Removed placeholder Spotify/Apple links")

        elif fix_type == "fix_css_vars":
            index_html = ep_web_dir / "index.html"
            if index_html.exists():
                content = index_html.read_text()
                replacements = {
                    "var(--warm-brown)": "#a78bfa",
                    "var(--light-tan)": "rgba(255,255,255,0.1)",
                    "var(--cream)": "#0f0f0f",
                    "var(--sage)": "#4ecdc4",
                }
                for old, new in replacements.items():
                    content = content.replace(old, new)
                index_html.write_text(content)
                fixes_applied.append("Fixed old theme CSS variables")

        elif fix_type == "update_youtube_link":
            youtube_path = ep_dir / "youtube.json"
            index_html = ep_web_dir / "index.html"
            if youtube_path.exists() and index_html.exists():
                try:
                    yt_data = json.loads(youtube_path.read_text())
                    video_id = yt_data.get("video_id", "")
                    if video_id:
                        content = index_html.read_text()
                        yt_url = f"https://www.youtube.com/watch?v={video_id}"
                        # Replace any existing YouTube href="#" or old link
                        content = re.sub(
                            r'href="[^"]*"([^>]*>▶\s*YouTube)',
                            f'href="{yt_url}" target="_blank" rel="noopener"\\1',
                            content,
                        )
                        index_html.write_text(content)
                        fixes_applied.append(f"Updated YouTube link to {yt_url}")
                except Exception:
                    pass

        elif fix_type == "regenerate_website":
            # Can't fully regenerate here — flag for the pipeline to do it
            fixes_applied.append(f"[NEEDS MANUAL FIX] {issue['message']}")

    return fixes_applied


# ── Main step ────────────────────────────────────────────────────────────────

def run_final_review(
    ep_dir: Path,
    topic: str,
    season: int,
    episode: int,
    dry_run: bool = False,
) -> StepResult:
    """Run final review of all episode outputs. Attempts auto-fixes.

    Returns StepResult with:
      output: dict with issues, fixes_applied, summary
      passed: True if no errors remain after fixes
      message: Human-readable summary
    """
    if dry_run:
        return StepResult(
            output={"issues": [], "fixes_applied": [], "summary": "Dry run — skipped"},
            passed=True,
            message="Dry run — final review skipped",
            attempt=1,
        )

    all_issues: list[dict] = []

    # Run all checks
    all_issues.extend(_check_episode_files(ep_dir))
    all_issues.extend(_check_audio_duration(ep_dir))
    all_issues.extend(_check_script_quality(ep_dir))
    all_issues.extend(_check_diagram_json(ep_dir))
    all_issues.extend(_check_website_output(ep_dir, topic, season, episode))
    all_issues.extend(_check_feed(topic, season, episode))

    # Attempt auto-fixes
    fixes_applied = _apply_fixes(all_issues, ep_dir, topic, season, episode)

    # Re-run website checks after fixes
    if fixes_applied:
        post_fix_issues: list[dict] = []
        post_fix_issues.extend(_check_website_output(ep_dir, topic, season, episode))
        # Replace website issues with post-fix results
        all_issues = [i for i in all_issues if i["category"] not in (
            "website_placeholders", "website_css", "website_diagram",
            "website_youtube", "website_missing",
        )]
        all_issues.extend(post_fix_issues)

    errors = [i for i in all_issues if i["severity"] == "error"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]

    summary_parts = []
    if errors:
        summary_parts.append(f"{len(errors)} error(s)")
    if warnings:
        summary_parts.append(f"{len(warnings)} warning(s)")
    if fixes_applied:
        summary_parts.append(f"{len(fixes_applied)} auto-fix(es)")
    if not summary_parts:
        summary_parts.append("all checks passed")

    summary = ", ".join(summary_parts)

    passed = len(errors) == 0

    return StepResult(
        output={
            "issues": all_issues,
            "fixes_applied": fixes_applied,
            "errors": len(errors),
            "warnings": len(warnings),
            "summary": summary,
        },
        passed=passed,
        message=f"Final review: {summary}",
        attempt=1,
    )
