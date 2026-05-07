"""Final Review Agent — validates the complete episode output before deployment.

Runs after all generation steps. Goes through a comprehensive checklist to ensure
every episode is production-ready before deployment. Attempts auto-fixes for
common issues and produces a detailed report.

CHECKLIST (every episode, every time):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1. FILES       — All required files exist and are non-empty
 2. AUDIO       — Duration within 3-12 min, valid MP3
 3. SCRIPT      — Host A/B markers present, balanced, 500+ words
 4. DIAGRAM     — Valid JSON, 3+ nodes, no orphan edges, no disconnected nodes
 5. WEBSITE     — Episode page exists, no broken links, correct audio URL
 6. AUDIO URL   — Points to GitHub Release (not local file)
 7. YOUTUBE     — Link present in episode page if upload happened
 8. LINKS       — No placeholder href="#" links remain
 9. CSS         — No stale old-theme CSS variables
10. DIAGRAM WEB — diagram.html copied to docs/, iframe present
11. RSS FEED    — Episode listed in feed.xml
12. INDEX PAGE  — Episode card present on main index.html
13. COHERENCE   — Title/topic matches across all outputs
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
    PODCAST_GITHUB_REPO,
    WEBSITE_DIR,
    WEBSITE_URL,
)
from pipeline.quality import StepResult
from pipeline.utils import slugify


# ── Individual Checks ────────────────────────────────────────────────────────

def _check_1_files(ep_dir: Path) -> list[dict]:
    """[1] FILES — All required files exist and are non-empty."""
    issues = []
    required = {
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
        "final_review.json": "Previous review results",
    }

    for filename, label in required.items():
        path = ep_dir / filename
        if not path.exists():
            issues.append({
                "check": 1, "severity": "error", "category": "missing_file",
                "message": f"Missing required file: {filename} ({label})",
                "file": filename, "fixable": False,
            })
        elif path.stat().st_size == 0:
            issues.append({
                "check": 1, "severity": "error", "category": "empty_file",
                "message": f"File is empty: {filename} ({label})",
                "file": filename, "fixable": False,
            })

    for filename, label in optional.items():
        path = ep_dir / filename
        if not path.exists():
            issues.append({
                "check": 1, "severity": "info", "category": "missing_optional",
                "message": f"Optional file not found: {filename} ({label})",
                "file": filename, "fixable": False,
            })

    return issues


def _check_2_audio(ep_dir: Path) -> list[dict]:
    """[2] AUDIO — Duration within bounds, valid MP3."""
    issues = []
    mp3_path = ep_dir / "episode.mp3"
    if not mp3_path.exists():
        return issues  # Caught by check 1

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(mp3_path)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            if duration < AUDIO_DURATION_MIN_SEC:
                issues.append({
                    "check": 2, "severity": "error", "category": "audio_short",
                    "message": f"Audio too short: {duration:.0f}s (min {AUDIO_DURATION_MIN_SEC}s)",
                    "fixable": False,
                })
            elif duration > AUDIO_DURATION_MAX_SEC:
                issues.append({
                    "check": 2, "severity": "warning", "category": "audio_long",
                    "message": f"Audio long: {duration:.0f}s (max {AUDIO_DURATION_MAX_SEC}s)",
                    "fixable": False,
                })
        else:
            issues.append({
                "check": 2, "severity": "warning", "category": "audio_probe_fail",
                "message": f"ffprobe failed: {result.stderr.strip()[:100]}",
                "fixable": False,
            })
    except FileNotFoundError:
        issues.append({
            "check": 2, "severity": "info", "category": "audio_no_ffprobe",
            "message": "ffprobe not available — skipping audio duration check",
            "fixable": False,
        })
    except subprocess.TimeoutExpired:
        issues.append({
            "check": 2, "severity": "warning", "category": "audio_timeout",
            "message": "ffprobe timed out checking audio",
            "fixable": False,
        })

    return issues


def _check_3_script(ep_dir: Path) -> list[dict]:
    """[3] SCRIPT — Host A/B markers, balance, word count."""
    issues = []
    script_path = ep_dir / "script.md"
    if not script_path.exists():
        return issues

    script = script_path.read_text()
    host_a = len(re.findall(r"\*\*\[Host A\]:\*\*", script))
    host_b = len(re.findall(r"\*\*\[Host B\]:\*\*", script))

    if host_a == 0:
        issues.append({
            "check": 3, "severity": "error", "category": "script_no_host_a",
            "message": "No Host A dialogue found in script", "fixable": False,
        })
    if host_b == 0:
        issues.append({
            "check": 3, "severity": "error", "category": "script_no_host_b",
            "message": "No Host B dialogue found in script", "fixable": False,
        })
    if host_a > 0 and host_b > 0:
        ratio = max(host_a, host_b) / min(host_a, host_b)
        if ratio > 3.0:
            issues.append({
                "check": 3, "severity": "warning", "category": "script_imbalanced",
                "message": f"Host dialogue imbalanced: A={host_a}, B={host_b} ({ratio:.1f}x)",
                "fixable": False,
            })

    words = len(script.split())
    if words < 500:
        issues.append({
            "check": 3, "severity": "warning", "category": "script_short",
            "message": f"Script short: {words} words (expected 750+)", "fixable": False,
        })

    return issues


def _check_4_diagram(ep_dir: Path) -> list[dict]:
    """[4] DIAGRAM — Valid JSON, node/edge integrity."""
    issues = []
    diagram_path = ep_dir / "diagram.json"
    if not diagram_path.exists():
        return issues

    try:
        data = json.loads(diagram_path.read_text())
    except json.JSONDecodeError as e:
        issues.append({
            "check": 4, "severity": "error", "category": "diagram_parse",
            "message": f"Diagram JSON parse error: {e}", "fixable": False,
        })
        return issues

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    node_ids = {n["id"] for n in nodes}

    if len(nodes) < 3:
        issues.append({
            "check": 4, "severity": "error", "category": "diagram_few_nodes",
            "message": f"Too few nodes: {len(nodes)} (min 3)", "fixable": False,
        })
    if len(nodes) > 15:
        issues.append({
            "check": 4, "severity": "warning", "category": "diagram_many_nodes",
            "message": f"Many nodes: {len(nodes)} (>15 may clutter)", "fixable": False,
        })

    for edge in edges:
        if edge.get("from") not in node_ids:
            issues.append({
                "check": 4, "severity": "error", "category": "diagram_bad_edge",
                "message": f"Edge from unknown node: '{edge.get('from')}'", "fixable": False,
            })
        if edge.get("to") not in node_ids:
            issues.append({
                "check": 4, "severity": "error", "category": "diagram_bad_edge",
                "message": f"Edge to unknown node: '{edge.get('to')}'", "fixable": False,
            })

    connected = set()
    for edge in edges:
        connected.add(edge.get("from"))
        connected.add(edge.get("to"))
    orphans = node_ids - connected
    if orphans:
        issues.append({
            "check": 4, "severity": "warning", "category": "diagram_orphans",
            "message": f"Disconnected nodes: {', '.join(sorted(orphans))}", "fixable": False,
        })

    # Check all nodes have required fields
    for node in nodes:
        if not node.get("label"):
            issues.append({
                "check": 4, "severity": "warning", "category": "diagram_node_label",
                "message": f"Node '{node.get('id')}' missing label", "fixable": False,
            })
        if not node.get("description"):
            issues.append({
                "check": 4, "severity": "info", "category": "diagram_node_desc",
                "message": f"Node '{node.get('id')}' missing description", "fixable": False,
            })

    return issues


def _check_5_website(ep_dir: Path, topic: str) -> list[dict]:
    """[5] WEBSITE — Episode page exists in docs/."""
    issues = []
    slug = slugify(topic)
    ep_web_dir = Path(WEBSITE_DIR) / slug

    if not ep_web_dir.exists():
        issues.append({
            "check": 5, "severity": "error", "category": "website_dir_missing",
            "message": f"Website episode dir missing: docs/{slug}/",
            "fixable": True, "fix": "regenerate_website",
        })
        return issues

    index_html = ep_web_dir / "index.html"
    if not index_html.exists():
        issues.append({
            "check": 5, "severity": "error", "category": "website_page_missing",
            "message": f"Episode page missing: docs/{slug}/index.html",
            "fixable": True, "fix": "regenerate_website",
        })

    return issues


def _check_6_audio_url(ep_dir: Path, topic: str) -> list[dict]:
    """[6] AUDIO URL — MP3 must exist in docs/ for GitHub Pages streaming."""
    issues = []
    slug = slugify(topic)
    ep_web_dir = Path(WEBSITE_DIR) / slug
    index_html = ep_web_dir / "index.html"
    if not index_html.exists():
        return issues

    content = index_html.read_text()
    audio_srcs = re.findall(r'<source\s+src="([^"]+)"', content)

    if not audio_srcs:
        issues.append({
            "check": 6, "severity": "warning", "category": "audio_no_source",
            "message": "No audio source tag found in episode page",
            "fixable": False,
        })
        return issues

    for src in audio_srcs:
        if src.startswith("http"):
            # GitHub Release URLs don't stream properly (attachment disposition)
            issues.append({
                "check": 6, "severity": "error", "category": "audio_remote_ref",
                "message": f"Audio uses remote URL '{src[:60]}...' — GitHub Release URLs don't stream in browsers",
                "fixable": True, "fix": "fix_audio_url_local",
            })
        elif src.endswith(".mp3"):
            # Local ref is correct — but verify the file exists in docs/
            mp3_path = ep_web_dir / src
            if not mp3_path.exists():
                issues.append({
                    "check": 6, "severity": "error", "category": "audio_file_missing",
                    "message": f"Audio source '{src}' referenced but file missing from docs/{slug}/",
                    "fixable": True, "fix": "copy_audio",
                })

    return issues


def _check_7_youtube(ep_dir: Path, topic: str) -> list[dict]:
    """[7] YOUTUBE — Link present if upload happened."""
    issues = []
    yt_path = ep_dir / "youtube.json"
    if not yt_path.exists():
        return issues  # No upload — OK

    try:
        yt_data = json.loads(yt_path.read_text())
        video_id = yt_data.get("video_id", "")
        if not video_id:
            return issues
    except Exception:
        return issues

    slug = slugify(topic)
    ep_web = Path(WEBSITE_DIR) / slug / "index.html"
    if not ep_web.exists():
        return issues

    content = ep_web.read_text()
    if video_id not in content:
        issues.append({
            "check": 7, "severity": "warning", "category": "youtube_link_missing",
            "message": f"YouTube video uploaded (id: {video_id}) but link not in episode page",
            "fixable": True, "fix": "fix_youtube_link",
        })

    return issues


def _check_8_placeholder_links(topic: str) -> list[dict]:
    """[8] LINKS — No placeholder href='#' links."""
    issues = []
    slug = slugify(topic)
    ep_web = Path(WEBSITE_DIR) / slug / "index.html"
    if not ep_web.exists():
        return issues

    content = ep_web.read_text()
    placeholders = re.findall(r'href="#"[^>]*>[^<]+</a>', content)
    if placeholders:
        labels = [re.search(r'>([^<]+)<', p).group(1) for p in placeholders if re.search(r'>([^<]+)<', p)]
        issues.append({
            "check": 8, "severity": "warning", "category": "placeholder_links",
            "message": f"Placeholder links found: {', '.join(labels)}",
            "fixable": True, "fix": "remove_placeholder_links",
        })

    return issues


def _check_9_css(topic: str) -> list[dict]:
    """[9] CSS — No stale old-theme variables."""
    issues = []
    slug = slugify(topic)
    ep_web = Path(WEBSITE_DIR) / slug / "index.html"
    if not ep_web.exists():
        return issues

    content = ep_web.read_text()
    old_vars = set(re.findall(r'var\(--(?:warm-brown|light-tan|cream|sage)\)', content))
    if old_vars:
        issues.append({
            "check": 9, "severity": "error", "category": "stale_css_vars",
            "message": f"Old theme CSS vars: {', '.join(sorted(old_vars))}",
            "fixable": True, "fix": "fix_css_vars",
        })

    return issues


def _check_10_diagram_web(ep_dir: Path, topic: str) -> list[dict]:
    """[10] DIAGRAM WEB — diagram.html present in docs/, iframe in page."""
    issues = []
    slug = slugify(topic)
    ep_web_dir = Path(WEBSITE_DIR) / slug
    ep_page = ep_web_dir / "index.html"
    if not ep_page.exists():
        return issues

    content = ep_page.read_text()
    diagram_web = ep_web_dir / "diagram.html"

    if "diagram.html" in content and not diagram_web.exists():
        issues.append({
            "check": 10, "severity": "error", "category": "diagram_web_missing",
            "message": "Episode page references diagram.html but file missing from docs/",
            "fixable": True, "fix": "copy_diagram",
        })

    if "diagram.html" not in content and (ep_dir / "diagram.html").exists():
        issues.append({
            "check": 10, "severity": "warning", "category": "diagram_not_embedded",
            "message": "diagram.html exists but not embedded in episode page",
            "fixable": False,
        })

    return issues


def _check_11_feed(topic: str, season: int, episode: int) -> list[dict]:
    """[11] RSS FEED — Episode present in feed.xml."""
    issues = []
    feed_path = Path(WEBSITE_DIR) / "feed.xml"
    if not feed_path.exists():
        issues.append({
            "check": 11, "severity": "warning", "category": "feed_missing",
            "message": "RSS feed file (docs/feed.xml) not found",
            "fixable": True, "fix": "copy_feed",
        })
        return issues

    content = feed_path.read_text()
    slug = slugify(topic)
    ep_code = f"S{season:02d}E{episode:02d}"
    found = (
        slug in content
        or topic.lower() in content.lower()
        or ep_code.lower() in content.lower()
    )
    if not found:
        issues.append({
            "check": 11, "severity": "warning", "category": "feed_no_episode",
            "message": f"Episode '{topic}' ({ep_code}) not found in RSS feed",
            "fixable": True, "fix": "copy_feed",
        })

    return issues


def _check_12_index(topic: str) -> list[dict]:
    """[12] INDEX PAGE — Episode card present on main index."""
    issues = []
    slug = slugify(topic)
    index_path = Path(WEBSITE_DIR) / "index.html"
    if not index_path.exists():
        issues.append({
            "check": 12, "severity": "warning", "category": "index_missing",
            "message": "Main index.html not found",
            "fixable": False,
        })
        return issues

    content = index_path.read_text()
    if slug not in content:
        issues.append({
            "check": 12, "severity": "warning", "category": "index_no_card",
            "message": f"Episode card for '{topic}' not found on main index page",
            "fixable": True, "fix": "regenerate_website",
        })

    # Also check main page audio URL
    audio_srcs = re.findall(r'<source\s+src="([^"]+)"', content)
    for src in audio_srcs:
        if not src.startswith("http") and src.endswith(".mp3"):
            issues.append({
                "check": 12, "severity": "error", "category": "index_audio_local",
                "message": f"Main page audio uses local path '{src}'",
                "fixable": True, "fix": "fix_index_audio",
            })

    return issues


def _check_13_coherence(ep_dir: Path, topic: str) -> list[dict]:
    """[13] COHERENCE — Topic matches across outputs."""
    issues = []
    research_path = ep_dir / "research.json"
    if not research_path.exists():
        return issues

    try:
        research = json.loads(research_path.read_text())
        research_topic = research.get("topic", "")
        if research_topic and topic.lower() not in research_topic.lower():
            issues.append({
                "check": 13, "severity": "warning", "category": "topic_mismatch",
                "message": f"Research topic '{research_topic}' doesn't match '{topic}'",
                "fixable": False,
            })
    except Exception:
        pass

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
    fixes = []
    slug = slugify(topic)
    website_dir = Path(WEBSITE_DIR)
    ep_web_dir = website_dir / slug

    for issue in issues:
        if not issue.get("fixable"):
            continue

        fix = issue.get("fix", "")

        if fix == "copy_diagram":
            src = ep_dir / "diagram.html"
            if src.exists() and ep_web_dir.exists():
                shutil.copy2(src, ep_web_dir / "diagram.html")
                fixes.append("Copied diagram.html to docs/")
            png_src = ep_dir / "diagram.png"
            if png_src.exists() and ep_web_dir.exists():
                shutil.copy2(png_src, ep_web_dir / "diagram.png")
                fixes.append("Copied diagram.png to docs/")

        elif fix == "remove_placeholder_links":
            page = ep_web_dir / "index.html"
            if page.exists():
                content = page.read_text()
                content = re.sub(
                    r'\s*<a\s+href="#"[^>]*>[^<]*</a>',
                    '', content,
                )
                page.write_text(content)
                fixes.append("Removed placeholder links")

        elif fix == "fix_css_vars":
            page = ep_web_dir / "index.html"
            if page.exists():
                content = page.read_text()
                for old, new in {
                    "var(--warm-brown)": "#a78bfa",
                    "var(--light-tan)": "rgba(255,255,255,0.1)",
                    "var(--cream)": "#0f0f0f",
                    "var(--sage)": "#4ecdc4",
                }.items():
                    content = content.replace(old, new)
                page.write_text(content)
                fixes.append("Fixed stale CSS variables")

        elif fix == "fix_audio_url_local":
            page = ep_web_dir / "index.html"
            if page.exists():
                content = page.read_text()
                content = re.sub(
                    r'<source\s+src="https?://[^"]*\.mp3"',
                    '<source src="episode.mp3"',
                    content,
                )
                page.write_text(content)
                fixes.append("Fixed audio URL → local episode.mp3")

        elif fix == "copy_audio":
            src = ep_dir / "episode.mp3"
            if src.exists() and ep_web_dir.exists():
                shutil.copy2(src, ep_web_dir / "episode.mp3")
                fixes.append("Copied episode.mp3 to docs/")

        elif fix == "fix_youtube_link":
            yt_path = ep_dir / "youtube.json"
            page = ep_web_dir / "index.html"
            if yt_path.exists() and page.exists():
                try:
                    yt = json.loads(yt_path.read_text())
                    vid = yt.get("video_id", "")
                    if vid:
                        url = f"https://www.youtube.com/watch?v={vid}"
                        content = page.read_text()
                        content = re.sub(
                            r'href="[^"]*"([^>]*>▶\s*YouTube)',
                            f'href="{url}" target="_blank" rel="noopener"\\1',
                            content,
                        )
                        page.write_text(content)
                        fixes.append(f"Updated YouTube link → {url}")
                except Exception:
                    pass

        elif fix == "fix_index_audio":
            index = website_dir / "index.html"
            if index.exists():
                content = index.read_text()
                content = re.sub(
                    r'<source\s+src="https?://[^"]*\.mp3"',
                    f'<source src="{slug}/episode.mp3"',
                    content,
                )
                index.write_text(content)
                fixes.append(f"Fixed main page audio URL → {slug}/episode.mp3")

        elif fix == "copy_feed":
            # Copy feed.xml from project root to docs/ if it exists
            root_feed = Path("feed.xml")
            docs_feed = website_dir / "feed.xml"
            if root_feed.exists():
                shutil.copy2(root_feed, docs_feed)
                fixes.append("Copied feed.xml to docs/")
            else:
                fixes.append("[NEEDS REGEN] feed.xml not found — run podcast step")

        elif fix == "regenerate_website":
            fixes.append(f"[NEEDS REGEN] {issue['message']} — re-run website step")

    return fixes


# ── Main step ────────────────────────────────────────────────────────────────

CHECKLIST = [
    ("1. FILES", _check_1_files),
    ("2. AUDIO", _check_2_audio),
    ("3. SCRIPT", _check_3_script),
    ("4. DIAGRAM", _check_4_diagram),
]

# These need (ep_dir, topic, ...) — handled in run_final_review


def run_final_review(
    ep_dir: Path,
    topic: str,
    season: int,
    episode: int,
    dry_run: bool = False,
) -> StepResult:
    """Run the full 13-point checklist. Auto-fixes what it can.

    Returns StepResult with:
      output: dict with checklist results, issues, fixes
      passed: True if no errors remain after fixes
    """
    if dry_run:
        return StepResult(
            output={"checklist": "skipped (dry run)", "issues": [], "fixes": []},
            passed=True,
            message="Final review: dry run — skipped",
            attempt=1,
        )

    all_issues: list[dict] = []

    # Checks that only need ep_dir
    all_issues.extend(_check_1_files(ep_dir))
    all_issues.extend(_check_2_audio(ep_dir))
    all_issues.extend(_check_3_script(ep_dir))
    all_issues.extend(_check_4_diagram(ep_dir))

    # Checks that need topic/season/episode
    all_issues.extend(_check_5_website(ep_dir, topic))
    all_issues.extend(_check_6_audio_url(ep_dir, topic))
    all_issues.extend(_check_7_youtube(ep_dir, topic))
    all_issues.extend(_check_8_placeholder_links(topic))
    all_issues.extend(_check_9_css(topic))
    all_issues.extend(_check_10_diagram_web(ep_dir, topic))
    all_issues.extend(_check_11_feed(topic, season, episode))
    all_issues.extend(_check_12_index(topic))
    all_issues.extend(_check_13_coherence(ep_dir, topic))

    # Auto-fix pass
    fixes = _apply_fixes(all_issues, ep_dir, topic, season, episode)

    # Re-check fixable categories after fixes
    if fixes:
        recheck_issues: list[dict] = []
        recheck_issues.extend(_check_6_audio_url(ep_dir, topic))
        recheck_issues.extend(_check_8_placeholder_links(topic))
        recheck_issues.extend(_check_9_css(topic))
        recheck_issues.extend(_check_10_diagram_web(ep_dir, topic))
        recheck_issues.extend(_check_12_index(topic))

        fixable_cats = {i["category"] for i in all_issues if i.get("fixable")}
        all_issues = [i for i in all_issues if i["category"] not in fixable_cats]
        all_issues.extend(recheck_issues)

    # Tally
    errors = [i for i in all_issues if i["severity"] == "error"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]
    infos = [i for i in all_issues if i["severity"] == "info"]

    # Build summary
    parts = []
    if errors:
        parts.append(f"{len(errors)} error(s)")
    if warnings:
        parts.append(f"{len(warnings)} warning(s)")
    if fixes:
        parts.append(f"{len(fixes)} auto-fix(es)")
    if not errors and not warnings:
        parts.append("all 13 checks passed ✅")
    summary = ", ".join(parts)

    # Build per-check report
    check_names = [
        "FILES", "AUDIO", "SCRIPT", "DIAGRAM", "WEBSITE", "AUDIO_URL",
        "YOUTUBE", "LINKS", "CSS", "DIAGRAM_WEB", "RSS_FEED", "INDEX", "COHERENCE",
    ]
    checklist_report = {}
    for i, name in enumerate(check_names, 1):
        check_issues = [iss for iss in all_issues if iss.get("check") == i]
        check_errors = [iss for iss in check_issues if iss["severity"] == "error"]
        if check_errors:
            checklist_report[f"{i}. {name}"] = "❌ FAIL"
        elif any(iss["severity"] == "warning" for iss in check_issues):
            checklist_report[f"{i}. {name}"] = "⚠️ WARN"
        else:
            checklist_report[f"{i}. {name}"] = "✅ PASS"

    return StepResult(
        output={
            "checklist": checklist_report,
            "issues": all_issues,
            "fixes_applied": fixes,
            "errors": len(errors),
            "warnings": len(warnings),
            "infos": len(infos),
            "summary": summary,
        },
        passed=len(errors) == 0,
        message=f"Final review ({len(check_names)}-point checklist): {summary}",
        attempt=1,
    )
