"""Audio generation using ElevenLabs v3 via Poe API — split, generate, stitch."""

import io
import os
import re
import tempfile
from pathlib import Path

import requests
from pydub import AudioSegment

from pipeline.config import (
    AUDIO_DURATION_MAX_SEC,
    AUDIO_DURATION_MIN_SEC,
    ELEVENLABS_V3_CHAR_LIMIT,
    ELEVENLABS_V3_MODEL,
)
from pipeline.quality import StepResult

# --- Audio tag mapping for v3 expressiveness ---
# Maps script cues to ElevenLabs v3 inline audio tags
EXPRESSION_MAP = {
    "*laughs*": "[laughs]",
    "*laugh*": "[laughs]",
    "*chuckles*": "[laughs softly]",
    "*pause*": "[thoughtful pause]",
    "*dramatic pause*": "[dramatic pause]",
    "*sighs*": "[sighs]",
    "*sigh*": "[sighs]",
    "*gasps*": "[surprised]",
}


def _convert_to_v3_format(script: str, host_a_name: str, host_b_name: str) -> str:
    """Convert **[Host A]:**/**[Host B]:** script to ElevenLabs v3 multi-speaker format.

    Output format:
        Liam: [enthusiastic] Welcome back to System Design Podcast!
        Bradford: [casual] Great to be here.
    """
    lines = []
    pattern = re.compile(r"\*\*\[Host ([AB])\]:\*\*\s*(.*)")

    for line in script.split("\n"):
        match = pattern.match(line.strip())
        if not match:
            continue

        speaker = match.group(1)
        text = match.group(2).strip()
        if not text:
            continue

        name = host_a_name if speaker == "A" else host_b_name

        # Convert script expression cues to v3 audio tags
        for old, new in EXPRESSION_MAP.items():
            text = text.replace(old, new)

        # Remove any remaining *italics* formatting
        text = re.sub(r"\*(.*?)\*", r"\1", text)

        lines.append(f"{name}: {text}")

    return "\n".join(lines)


def _chunk_dialogue(dialogue: str, char_limit: int) -> list[str]:
    """Split dialogue into chunks that fit within the ElevenLabs v3 char limit.

    Rules:
    - Never split mid-line (each line = one speaker turn)
    - Aim for chunks close to char_limit
    - Each chunk maintains proper Speaker: format
    """
    lines = dialogue.split("\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > char_limit and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_len = 0

        current_chunk.append(line)
        current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def _call_elevenlabs_v3(text: str) -> bytes:
    """Call ElevenLabs v3 via Poe's OpenAI-compatible API and return MP3 bytes."""
    api_key = os.environ.get("POE_API_KEY")
    if not api_key:
        raise RuntimeError("POE_API_KEY not set")

    response = requests.post(
        "https://api.poe.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": ELEVENLABS_V3_MODEL,
            "stream": False,
            "messages": [{"role": "user", "content": text}],
        },
        timeout=180,
    )
    response.raise_for_status()

    data = response.json()
    audio_url = data["choices"][0]["message"]["content"]

    # Download the audio file
    audio_response = requests.get(audio_url, timeout=60)
    audio_response.raise_for_status()
    return audio_response.content


def generate_audio_v3(
    script: str,
    host_a_voice: str,
    host_b_voice: str,
    output_path: Path,
    dry_run: bool = False,
) -> Path:
    """Generate MP3 from script using ElevenLabs v3 via Poe API.

    Pipeline: script → convert to v3 format → chunk → generate per chunk → stitch.
    """
    # Convert script to v3 multi-speaker format
    dialogue = _convert_to_v3_format(script, host_a_voice, host_b_voice)

    if not dialogue.strip():
        raise ValueError("No dialogue lines found in script")

    print(f"  Converted script to v3 format ({len(dialogue)} chars)")

    if dry_run:
        silence = AudioSegment.silent(duration=5000)
        silence.export(str(output_path), format="mp3")
        return output_path

    # Chunk the dialogue
    chunks = _chunk_dialogue(dialogue, ELEVENLABS_V3_CHAR_LIMIT)
    print(f"  Split into {len(chunks)} chunks (limit: {ELEVENLABS_V3_CHAR_LIMIT} chars)")

    for i, chunk in enumerate(chunks):
        print(f"    Chunk {i+1}: {len(chunk)} chars, "
              f"{chunk.count(chr(10))+1} lines")

    # Generate audio for each chunk
    audio_segments: list[AudioSegment] = []
    for i, chunk in enumerate(chunks):
        print(f"  Generating chunk {i+1}/{len(chunks)}...")
        audio_bytes = _call_elevenlabs_v3(chunk)
        segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
        audio_segments.append(segment)
        print(f"    → {len(segment)/1000:.1f}s")

    # Stitch chunks together with a brief pause and add a soft landing at the end
    combined = audio_segments[0]
    for segment in audio_segments[1:]:
        # 200ms silence between chunks for natural transition
        combined += AudioSegment.silent(duration=200) + segment

    # Avoid the episode ending on a hard cutoff.
    combined += AudioSegment.silent(duration=900)

    combined.export(str(output_path), format="mp3")
    print(f"  Final audio: {len(combined)/1000:.1f}s → {output_path}")
    return output_path


def run_audio_v3(
    script: str,
    host_a_voice: str,
    host_b_voice: str,
    output_path: Path,
    dry_run: bool = False,
) -> StepResult:
    """Execute the ElevenLabs v3 audio generation step with quality gates."""
    try:
        generate_audio_v3(script, host_a_voice, host_b_voice, output_path, dry_run=dry_run)
    except Exception as e:
        return StepResult(
            output=str(output_path),
            passed=False,
            message=f"Audio generation failed: {e}",
            attempt=1,
        )

    if not output_path.exists():
        return StepResult(
            output=str(output_path),
            passed=False,
            message="Audio file was not created",
            attempt=1,
        )

    audio = AudioSegment.from_mp3(str(output_path))
    duration_sec = len(audio) / 1000

    if duration_sec < AUDIO_DURATION_MIN_SEC:
        return StepResult(
            output=str(output_path),
            passed=False,
            message=f"Audio too short: {duration_sec:.0f}s (min {AUDIO_DURATION_MIN_SEC}s)",
            attempt=1,
        )

    if duration_sec > AUDIO_DURATION_MAX_SEC:
        msg = f"Audio duration: {duration_sec:.0f}s (over {AUDIO_DURATION_MAX_SEC}s soft max, but OK)"
    else:
        msg = f"Audio duration: {duration_sec:.0f}s"

    return StepResult(output=str(output_path), passed=True, message=msg, attempt=1)
