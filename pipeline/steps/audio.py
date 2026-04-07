"""Step 5: Audio Generation — convert script to multi-voice MP3 using OpenAI TTS."""

import io
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydub import AudioSegment

from pipeline.config import AUDIO_DURATION_MAX_SEC, AUDIO_DURATION_MIN_SEC
from pipeline.llm import call_openai_tts
from pipeline.quality import StepResult


def parse_script_lines(script: str) -> list[dict[str, str]]:
    """Parse script into individual lines with speaker labels.

    Returns list of {"speaker": "A"|"B", "text": "..."}.
    """
    lines: list[dict[str, str]] = []
    pattern = re.compile(r"\*\*\[Host ([AB])\]:\*\*\s*(.*)")
    for line in script.split("\n"):
        match = pattern.match(line.strip())
        if match:
            speaker = match.group(1)
            text = match.group(2).strip()
            if text:
                lines.append({"speaker": speaker, "text": text})
    return lines


def generate_audio(
    script: str,
    host_a_voice: str,
    host_b_voice: str,
    output_path: Path,
    dry_run: bool = False,
) -> Path:
    """Generate MP3 from script lines using OpenAI TTS."""
    lines = parse_script_lines(script)
    if not lines:
        raise ValueError("No dialogue lines found in script")

    if dry_run:
        # Create a short silent audio file for dry-run
        silence = AudioSegment.silent(duration=5000)  # 5 seconds
        silence.export(str(output_path), format="mp3")
        return output_path

    # Per-speaker voice instructions
    VOICE_INSTRUCTIONS = {
        "A": (
            "Speak in a confident, knowledgeable podcast host style. "
            "Clear articulation with natural enthusiasm when explaining technical concepts."
        ),
        "B": (
            "Speak in an engaged, curious podcast co-host style. "
            "Show genuine interest with varied intonation. React naturally to explanations."
        ),
    }

    # Generate all TTS segments in parallel
    def _generate_segment(index: int, line: dict) -> tuple[int, bytes]:
        """Generate TTS for a single line; returns (index, audio_bytes)."""
        voice = host_a_voice if line["speaker"] == "A" else host_b_voice
        instructions = VOICE_INSTRUCTIONS[line["speaker"]]
        audio_bytes = call_openai_tts(line["text"], voice=voice, instructions=instructions)
        return index, audio_bytes

    print(f"  Generating {len(lines)} audio segments in parallel (max 5 workers)...")
    results: dict[int, bytes] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_generate_segment, i, line): i
            for i, line in enumerate(lines)
        }
        for future in as_completed(futures):
            idx, audio_bytes = future.result()
            results[idx] = audio_bytes
            print(f"  Completed segment {idx + 1}/{len(lines)} (Host {lines[idx]['speaker']})")

    # Concatenate segments IN ORDER, inserting silence between different speakers
    combined = AudioSegment.empty()
    for i in range(len(lines)):
        segment = AudioSegment.from_mp3(io.BytesIO(results[i]))
        combined += segment

        # Add 300ms pause only when the next line is a different speaker
        if i + 1 < len(lines) and lines[i + 1]["speaker"] != lines[i]["speaker"]:
            combined += AudioSegment.silent(duration=300)

    combined.export(str(output_path), format="mp3")
    return output_path


def _validate_audio(output_path: Path) -> tuple[bool, str]:
    """Validate the generated audio file."""
    if not output_path.exists():
        return False, "Audio file was not created"

    audio = AudioSegment.from_mp3(str(output_path))
    duration_sec = len(audio) / 1000

    if duration_sec < AUDIO_DURATION_MIN_SEC:
        return False, f"Audio too short: {duration_sec:.0f}s (min {AUDIO_DURATION_MIN_SEC}s)"
    if duration_sec > AUDIO_DURATION_MAX_SEC:
        # Soft limit — warn but pass
        return True, f"Audio duration: {duration_sec:.0f}s (over {AUDIO_DURATION_MAX_SEC}s soft max, but OK)"

    return True, f"Audio duration: {duration_sec:.0f}s"


def run_audio(
    script: str,
    host_a_voice: str,
    host_b_voice: str,
    output_path: Path,
    dry_run: bool = False,
) -> StepResult:
    """Execute the audio generation step with quality gates."""
    generate_audio(script, host_a_voice, host_b_voice, output_path, dry_run=dry_run)
    passed, message = _validate_audio(output_path)
    return StepResult(output=str(output_path), passed=passed, message=message, attempt=1)
