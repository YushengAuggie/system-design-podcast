"""Pipeline orchestrator and Click CLI for podcast episode generation."""

import json
import sys
from pathlib import Path

import click

from pipeline.config import DIAGRAM_REVIEW_MAX_CYCLES, REVIEW_MAX_CYCLES
from pipeline.quality import StepResult
from pipeline.config import TTS_ENGINE
from pipeline.steps.audio import run_audio
from pipeline.steps.audio_v3 import run_audio_v3
from pipeline.steps.diagram import run_diagram, _json_to_mermaid, _render_html
from pipeline.steps.diagram_review import run_diagram_review
from pipeline.steps.podcast import run_podcast
from pipeline.steps.research import run_research
from pipeline.steps.review import run_review
from pipeline.steps.screenshot import run_screenshot
from pipeline.steps.script import run_script
from pipeline.steps.voices import run_voices
from pipeline.steps.website import run_website
from pipeline.steps.youtube import run_youtube
from pipeline.steps.final_review import run_final_review
from pipeline.utils import episode_dir, load_json, load_text, save_json, save_text

# Ordered pipeline steps
STEPS = [
    "research", "script", "review", "voices", "audio",
    "diagram", "diagram_review", "screenshot",
    "youtube", "podcast", "website", "final_review",
]


def _print_step(name: str, status: str, message: str = "") -> None:
    """Pretty-print step status."""
    icon = {"running": ">>>", "passed": "[OK]", "failed": "[FAIL]"}
    prefix = icon.get(status, "   ")
    line = f"  {prefix} {name}"
    if message:
        line += f" — {message}"
    print(line)


def run_pipeline(
    topic: str,
    season: int,
    episode: int,
    start_step: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run the full pipeline (or from a specific step)."""
    ep_dir = episode_dir(season, episode, topic)
    print(f"Episode directory: {ep_dir}")
    print(f"Topic: {topic} | Season {season}, Episode {episode}")
    if dry_run:
        print("MODE: dry-run (no API calls)\n")
    print()

    # Determine which steps to run
    if start_step:
        if start_step not in STEPS:
            print(f"Unknown step: {start_step}. Valid steps: {', '.join(STEPS)}")
            sys.exit(1)
        steps_to_run = STEPS[STEPS.index(start_step):]
    else:
        steps_to_run = STEPS

    # Carry state between steps
    research_data: dict = {}
    script_text: str = ""
    voice_pair: dict = {}
    diagram_data: dict = {}

    # Load prior outputs if starting from a later step
    if start_step and start_step != "research":
        research_path = ep_dir / "research.json"
        if research_path.exists():
            research_data = load_json(research_path)
            print(f"  Loaded prior research from {research_path}")

    if start_step and start_step not in ("research", "script", "review"):
        script_path = ep_dir / "script.md"
        if script_path.exists():
            script_text = load_text(script_path)
            print(f"  Loaded prior script from {script_path}")

    if start_step and start_step == "audio":
        voice_path = ep_dir / "voices.json"
        if voice_path.exists():
            voice_pair = load_json(voice_path)
            print(f"  Loaded prior voice selection from {voice_path}")

    if start_step and start_step in ("diagram_review", "screenshot"):
        diagram_path = ep_dir / "diagram.json"
        if diagram_path.exists():
            diagram_data = load_json(diagram_path)
            print(f"  Loaded prior diagram from {diagram_path}")

    print()

    # --- Step: Research ---
    if "research" in steps_to_run:
        _print_step("Research", "running")
        result = run_research(topic, season, episode, dry_run=dry_run)
        _print_step("Research", "passed" if result.passed else "failed", result.message)
        if not result.passed:
            print(f"\nPipeline stopped: Research step failed — {result.message}")
            sys.exit(1)
        research_data = result.output
        save_json(ep_dir / "research.json", research_data)

    # --- Step: Script + Review loop ---
    if "script" in steps_to_run or "review" in steps_to_run:
        run_script_step = "script" in steps_to_run
        run_review_step = "review" in steps_to_run
        review_feedback = ""

        for cycle in range(1, REVIEW_MAX_CYCLES + 1):
            # Generate / revise script
            if run_script_step:
                _print_step("Script Generation", "running", f"cycle {cycle}")
                script_result = run_script(
                    research_data,
                    topic,
                    season,
                    episode,
                    dry_run=dry_run,
                    review_feedback=review_feedback,
                    previous_script=script_text,
                )
                _print_step(
                    "Script Generation",
                    "passed" if script_result.passed else "failed",
                    script_result.message,
                )
                if not script_result.passed:
                    print(f"\nPipeline stopped: Script generation failed — {script_result.message}")
                    sys.exit(1)
                script_text = script_result.output
                save_text(ep_dir / "script.md", script_text)

            # Review panel
            if run_review_step:
                _print_step("Review Panel", "running", f"cycle {cycle}")
                review_result = run_review(script_text, research_data, dry_run=dry_run)
                _print_step(
                    "Review Panel",
                    "passed" if review_result.passed else "failed",
                    review_result.message,
                )
                save_json(ep_dir / "review.json", review_result.output)

                if review_result.passed:
                    break

                if cycle < REVIEW_MAX_CYCLES:
                    review_feedback = "\n".join(review_result.output.get("combined_feedback", []))
                    print(f"  Sending feedback for revision:\n{review_feedback}\n")
                    # On next cycle, script step will regenerate
                    run_script_step = True
                else:
                    print(
                        f"\nPipeline stopped: Review panel failed after {REVIEW_MAX_CYCLES} cycles"
                    )
                    sys.exit(1)
            else:
                break  # No review step requested

    # --- Step: Voice Selection ---
    if "voices" in steps_to_run:
        _print_step("Voice Selection", "running")
        voice_result = run_voices(season, episode)
        _print_step("Voice Selection", "passed", voice_result.message)
        voice_pair = voice_result.output
        save_json(ep_dir / "voices.json", voice_pair)

    # --- Step: Audio Generation ---
    if "audio" in steps_to_run:
        if not script_text:
            script_path = ep_dir / "script.md"
            if script_path.exists():
                script_text = load_text(script_path)
            else:
                print("\nPipeline stopped: No script available for audio generation")
                sys.exit(1)
        if not voice_pair:
            print("\nPipeline stopped: No voice selection available for audio generation")
            sys.exit(1)

        _print_step("Audio Generation", "running", f"engine: {TTS_ENGINE}")
        audio_path = ep_dir / "episode.mp3"
        tts_engine = voice_pair.get("tts_engine", TTS_ENGINE)
        if tts_engine == "elevenlabs-v3":
            audio_result = run_audio_v3(
                script_text,
                voice_pair["host_a_voice"],
                voice_pair["host_b_voice"],
                audio_path,
                dry_run=dry_run,
            )
        else:
            audio_result = run_audio(
                script_text,
                voice_pair["host_a_voice"],
                voice_pair["host_b_voice"],
                audio_path,
                dry_run=dry_run,
            )
        _print_step(
            "Audio Generation",
            "passed" if audio_result.passed else "failed",
            audio_result.message,
        )
        if not audio_result.passed:
            print(f"\nPipeline stopped: Audio generation failed — {audio_result.message}")
            sys.exit(1)

    # --- Step: Diagram Generation + Review loop ---
    if "diagram" in steps_to_run or "diagram_review" in steps_to_run:
        if not script_text:
            script_path = ep_dir / "script.md"
            if script_path.exists():
                script_text = load_text(script_path)

        run_diagram_step = "diagram" in steps_to_run
        run_diagram_review_step = "diagram_review" in steps_to_run

        for cycle in range(1, DIAGRAM_REVIEW_MAX_CYCLES + 1):
            # Generate diagram
            if run_diagram_step:
                _print_step("Diagram Generation", "running", f"cycle {cycle}")
                diagram_result = run_diagram(research_data, script_text, dry_run=dry_run, ep_dir=ep_dir)
                _print_step(
                    "Diagram Generation",
                    "passed" if diagram_result.passed else "failed",
                    diagram_result.message,
                )

                if diagram_result.passed:
                    diagram_data = diagram_result.output
                    # Save all diagram outputs
                    save_json(ep_dir / "diagram.json", diagram_data)
                    mermaid_code = _json_to_mermaid(diagram_data)
                    save_text(ep_dir / "diagram.mmd", mermaid_code)
                    html_content = _render_html(diagram_data)
                    save_text(ep_dir / "diagram.html", html_content)
                    print(f"  Saved: diagram.json, diagram.html, diagram.mmd")
                else:
                    print(f"\nWarning: Diagram generation failed — {diagram_result.message}")
                    # Save what we have
                    if diagram_result.output:
                        save_json(ep_dir / "diagram.json", diagram_result.output)
                    break

            # Review diagram
            if run_diagram_review_step and diagram_data:
                _print_step("Diagram Review", "running", f"cycle {cycle}")
                review_result = run_diagram_review(
                    diagram_data, research_data, script_text, dry_run=dry_run,
                )
                _print_step(
                    "Diagram Review",
                    "passed" if review_result.passed else "failed",
                    review_result.message,
                )
                save_json(ep_dir / "diagram_review.json", review_result.output)

                if review_result.passed:
                    break

                if cycle < DIAGRAM_REVIEW_MAX_CYCLES:
                    print(f"  Regenerating diagram with feedback...")
                    run_diagram_step = True
                else:
                    print(f"\nWarning: Diagram review failed after {DIAGRAM_REVIEW_MAX_CYCLES} cycles (non-fatal)")
                    break
            else:
                break

    # --- Step: Screenshot ---
    if "screenshot" in steps_to_run:
        html_path = ep_dir / "diagram.html"
        png_path = ep_dir / "diagram.png"

        if html_path.exists():
            _print_step("Screenshot", "running")
            screenshot_result = run_screenshot(html_path, png_path, dry_run=dry_run)
            _print_step(
                "Screenshot",
                "passed" if screenshot_result.passed else "failed",
                screenshot_result.message,
            )
            if not screenshot_result.passed:
                print(f"\nWarning: Screenshot failed — {screenshot_result.message} (non-fatal)")
        else:
            print("  Skipping screenshot: no diagram.html found")

    # --- Step: YouTube Upload ---
    if "youtube" in steps_to_run:
        if not research_data:
            research_path = ep_dir / "research.json"
            if research_path.exists():
                research_data = load_json(research_path)

        _print_step("YouTube Upload", "running")
        youtube_result = run_youtube(
            episode_dir=ep_dir,
            topic=topic,
            season=season,
            episode=episode,
            research=research_data,
            dry_run=dry_run,
        )
        _print_step(
            "YouTube Upload",
            "passed" if youtube_result.passed else "failed",
            youtube_result.message,
        )
        if not youtube_result.passed:
            print(f"\nWarning: YouTube upload failed — {youtube_result.message}")
            # Non-fatal: pipeline still completes
        elif not dry_run:
            print(f"  Video URL: {youtube_result.output}")
            save_json(
                ep_dir / "youtube.json",
                {
                    "video_id": str(youtube_result.output).split("v=")[-1],
                    "url": youtube_result.output,
                    "title": f"System Design: {topic} | S{season:02d}E{episode:02d}",
                    "privacy": "unlisted",
                    "voices": f"{voice_pair.get('tts_engine', TTS_ENGINE)} ({voice_pair.get('host_a_voice', '?')} + {voice_pair.get('host_b_voice', '?')})",
                },
            )

    # --- Step: Podcast RSS Feed ---
    if "podcast" in steps_to_run:
        if not research_data:
            research_path = ep_dir / "research.json"
            if research_path.exists():
                research_data = load_json(research_path)

        _print_step("Podcast RSS Feed", "running")
        podcast_result = run_podcast(
            episode_dir=ep_dir,
            topic=topic,
            season=season,
            episode=episode,
            research_data=research_data,
            dry_run=dry_run,
        )
        _print_step(
            "Podcast RSS Feed",
            "passed" if podcast_result.passed else "failed",
            podcast_result.message,
        )
        if not podcast_result.passed:
            print(f"\nWarning: Podcast RSS step failed — {podcast_result.message}")
            # Non-fatal: pipeline still completes
        else:
            print(f"  Feed updated: {podcast_result.output}")

    # --- Step: Website Generation ---
    if "website" in steps_to_run:
        _print_step("Website Generation", "running")
        website_result = run_website(dry_run=dry_run)
        _print_step(
            "Website Generation",
            "passed" if website_result.passed else "failed",
            website_result.message,
        )
        if not website_result.passed:
            print(f"\nWarning: Website generation failed — {website_result.message}")
            # Non-fatal: pipeline still completes
        else:
            print(f"  Website updated: {website_result.output}/")

    # --- Step: Final Review ---
    if "final_review" in steps_to_run:
        _print_step("Final Review", "running")
        final_result = run_final_review(
            ep_dir=ep_dir,
            topic=topic,
            season=season,
            episode=episode,
            dry_run=dry_run,
        )
        _print_step(
            "Final Review",
            "passed" if final_result.passed else "failed",
            final_result.message,
        )
        save_json(ep_dir / "final_review.json", final_result.output)

        # Print checklist
        checklist = final_result.output.get("checklist", {})
        if isinstance(checklist, dict):
            print("\n    ━━━ CHECKLIST ━━━")
            for check, status in checklist.items():
                print(f"    {status} {check}")
            print()

        if final_result.output.get("fixes_applied"):
            print("    Auto-fixes applied:")
            for fix in final_result.output["fixes_applied"]:
                print(f"      🔧 {fix}")
            print()

        issues = [i for i in final_result.output.get("issues", [])
                  if i.get("severity") in ("error", "warning")]
        if issues:
            print("    Remaining issues:")
            for issue in issues:
                icon = "❌" if issue["severity"] == "error" else "⚠️"
                print(f"      {icon} {issue['message']}")
            print()

        if not final_result.passed:
            print(f"\n⚠️  Final review found errors — episode may not be production-ready")

    print("\nPipeline complete!")
    print(f"Outputs saved to: {ep_dir}/")


@click.group()
def cli() -> None:
    """System Design Podcast generation pipeline."""


@cli.command()
@click.option("--topic", required=True, help="Topic name (e.g., 'URL Shortener')")
@click.option("--season", required=True, type=int, help="Season number (1-4)")
@click.option("--episode", required=True, type=int, help="Episode number")
@click.option("--step", default=None, help=f"Start from step: {', '.join(STEPS)}")
@click.option("--dry-run", is_flag=True, help="Skip API calls, use mock data")
def generate(topic: str, season: int, episode: int, step: str | None, dry_run: bool) -> None:
    """Generate a podcast episode."""
    run_pipeline(topic, season, episode, start_step=step, dry_run=dry_run)
