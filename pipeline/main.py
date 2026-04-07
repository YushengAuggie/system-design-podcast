"""Pipeline orchestrator and Click CLI for podcast episode generation."""

import json
import sys
from pathlib import Path

import click

from pipeline.config import REVIEW_MAX_CYCLES
from pipeline.quality import StepResult
from pipeline.steps.audio import run_audio
from pipeline.steps.diagram import run_diagram
from pipeline.steps.research import run_research
from pipeline.steps.review import run_review
from pipeline.steps.script import run_script
from pipeline.steps.voices import run_voices
from pipeline.utils import episode_dir, load_json, load_text, save_json, save_text

# Ordered pipeline steps
STEPS = ["research", "script", "review", "voices", "audio", "diagram"]


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

        _print_step("Audio Generation", "running")
        audio_path = ep_dir / "episode.mp3"
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

    # --- Step: Diagram Generation ---
    if "diagram" in steps_to_run:
        if not script_text:
            script_path = ep_dir / "script.md"
            if script_path.exists():
                script_text = load_text(script_path)

        _print_step("Diagram Generation", "running")
        diagram_result = run_diagram(research_data, script_text, dry_run=dry_run)
        _print_step(
            "Diagram Generation",
            "passed" if diagram_result.passed else "failed",
            diagram_result.message,
        )
        if diagram_result.passed:
            save_text(ep_dir / "diagram.mmd", diagram_result.output)
        else:
            print(f"\nWarning: Diagram generation failed — {diagram_result.message}")
            # Non-fatal: save what we have anyway
            save_text(ep_dir / "diagram.mmd", diagram_result.output)

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
