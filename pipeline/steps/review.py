"""Step 3: Script Review — three-agent panel (Fact Checker, Vibe, Engineering Constraints)."""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from pipeline.config import (
    EXPECTED_SEGMENTS,
    SCRIPT_WORD_MAX,
    SCRIPT_WORD_MIN,
    SCRIPT_WORD_SOFT_MAX,
    VIBE_SCORE_MIN,
)
from pipeline.llm import call_anthropic
from pipeline.quality import StepResult
from pipeline.utils import word_count

# ---------------------------------------------------------------------------
# Agent 1: Fact Checker
# ---------------------------------------------------------------------------

FACT_CHECK_SYSTEM = """\
You are a technical fact checker for a system design podcast. Review the script for:
- Accuracy of technical claims and system design statements
- Correctness of architecture descriptions
- Validity of company references (are these real companies doing what's described?)
- Any hallucinated or incorrect technical details

Return your review as:
VERDICT: PASS or FAIL
ISSUES:
- (list each issue, or "None" if all checks pass)
"""


def _run_fact_checker(script: str, research: dict) -> dict:
    """Agent 1: Check technical accuracy."""
    prompt = f"Review this podcast script for technical accuracy.\n\nSCRIPT:\n{script}"
    raw = call_anthropic(prompt, system=FACT_CHECK_SYSTEM, temperature=0.3)
    verdict = "PASS" if "VERDICT: PASS" in raw.upper() else "FAIL"
    issues = []
    if "ISSUES:" in raw:
        issues_text = raw.split("ISSUES:", 1)[1].strip()
        for line in issues_text.split("\n"):
            line = line.strip().lstrip("- ")
            if line and line.lower() != "none":
                issues.append(line)
    return {"agent": "fact_checker", "passed": verdict == "PASS", "issues": issues, "raw": raw}


# ---------------------------------------------------------------------------
# Agent 2: Vibe & Broadcast Quality
# ---------------------------------------------------------------------------

VIBE_SYSTEM = """\
You are a podcast producer reviewing a script for broadcast quality. Evaluate:
- Natural conversation flow (does it sound like two friends talking?)
- Word choice (conversational, not textbook)
- Entertainment value, pacing, hooks, energy
- Would a listener stay engaged for the full episode?

Return your review as:
VIBE_SCORE: [1-10]
VERDICT: PASS or FAIL (must score >= 7 to pass)
FEEDBACK:
- (specific feedback points)
"""


def _run_vibe_checker(script: str) -> dict:
    """Agent 2: Check conversational quality and engagement."""
    prompt = f"Review this podcast script for vibe and broadcast quality.\n\nSCRIPT:\n{script}"
    raw = call_anthropic(prompt, system=VIBE_SYSTEM, temperature=0.5)

    # Parse vibe score
    score_match = re.search(r"VIBE_SCORE:\s*(\d+)", raw)
    score = int(score_match.group(1)) if score_match else 0

    passed = score >= VIBE_SCORE_MIN

    feedback = []
    if "FEEDBACK:" in raw:
        fb_text = raw.split("FEEDBACK:", 1)[1].strip()
        for line in fb_text.split("\n"):
            line = line.strip().lstrip("- ")
            if line:
                feedback.append(line)

    return {
        "agent": "vibe_checker",
        "passed": passed,
        "score": score,
        "feedback": feedback,
        "raw": raw,
    }


# ---------------------------------------------------------------------------
# Agent 3: Engineering Constraints (deterministic where possible)
# ---------------------------------------------------------------------------


def _run_engineering_constraints(script: str) -> dict:
    """Agent 3: Check word count, format, segments — deterministic code checks."""
    issues: list[str] = []

    warnings: list[str] = []

    # Word count check (deterministic)
    wc = word_count(script)
    if wc < SCRIPT_WORD_MIN:
        issues.append(f"Word count too low: {wc} (min {SCRIPT_WORD_MIN})")
    elif wc > SCRIPT_WORD_SOFT_MAX:
        issues.append(f"Word count too high: {wc} (soft max {SCRIPT_WORD_SOFT_MAX})")
    elif wc > SCRIPT_WORD_MAX:
        warnings.append(f"Word count above target max: {wc} (target max {SCRIPT_WORD_MAX}, soft max {SCRIPT_WORD_SOFT_MAX})")

    # Host A/B label check (deterministic)
    host_a_lines = re.findall(r"\*\*\[Host A\]\:\*\*", script)
    host_b_lines = re.findall(r"\*\*\[Host B\]\:\*\*", script)
    if not host_a_lines:
        issues.append("No Host A dialogue lines found")
    if not host_b_lines:
        issues.append("No Host B dialogue lines found")

    # Segment check (deterministic)
    segment_headers = re.findall(r"^## Segment \d", script, re.MULTILINE)
    if len(segment_headers) < EXPECTED_SEGMENTS:
        issues.append(
            f"Expected {EXPECTED_SEGMENTS} segments, found {len(segment_headers)}"
        )

    # References section check (deterministic)
    has_references = bool(re.search(r"^## References", script, re.MULTILINE))
    if not has_references:
        issues.append("Missing References section")

    # URL check (deterministic)
    urls = re.findall(r"https?://[^\s)]+", script)
    if not urls:
        issues.append("No URLs found in references section")

    # Segment balance (use LLM only for subjective assessment if segments exist)
    if len(segment_headers) >= EXPECTED_SEGMENTS:
        segments = re.split(r"^## Segment \d", script, flags=re.MULTILINE)
        # segments[0] is metadata before first segment, segments[1:] are the 5 segments
        segment_bodies = segments[1:] if len(segments) > 1 else []
        for i, seg in enumerate(segment_bodies, 1):
            seg_wc = len(seg.split())
            if seg_wc < 20:
                issues.append(f"Segment {i} appears too short ({seg_wc} words)")

    passed = len(issues) == 0
    checklist = {
        "warnings": warnings,
        "word_count": wc,
        "word_count_ok": SCRIPT_WORD_MIN <= wc <= SCRIPT_WORD_SOFT_MAX,
        "host_a_lines": len(host_a_lines),
        "host_b_lines": len(host_b_lines),
        "segments_found": len(segment_headers),
        "has_references": has_references,
        "url_count": len(urls),
    }

    return {
        "agent": "engineering_constraints",
        "passed": passed,
        "issues": issues,
        "checklist": checklist,
    }


# ---------------------------------------------------------------------------
# Combined review panel
# ---------------------------------------------------------------------------


def _run_review_panel(script: str, research: dict, dry_run: bool = False) -> dict:
    """Run all three review agents in parallel and combine verdicts."""
    if dry_run:
        return _mock_review(script)

    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_run_fact_checker, script, research): "fact_checker",
            executor.submit(_run_vibe_checker, script): "vibe_checker",
            executor.submit(_run_engineering_constraints, script): "engineering_constraints",
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                # Individual agent failure — record as failed result rather than crashing
                results[name] = {
                    "agent": name,
                    "passed": False,
                    "issues": [f"Agent raised an exception: {exc}"],
                    "raw": str(exc),
                }

    all_passed = all(r["passed"] for r in results.values())

    # Collect all feedback for revision
    combined_feedback: list[str] = []
    for name, result in results.items():
        if not result["passed"]:
            agent_label = name.replace("_", " ").title()
            if "issues" in result and result["issues"]:
                for issue in result["issues"]:
                    combined_feedback.append(f"[{agent_label}] {issue}")
            if "feedback" in result and result["feedback"]:
                for fb in result["feedback"]:
                    combined_feedback.append(f"[{agent_label}] {fb}")

    return {
        "agents": results,
        "all_passed": all_passed,
        "combined_feedback": combined_feedback,
    }


def _mock_review(script: str) -> dict:
    """Return mock review for dry-run mode."""
    eng = _run_engineering_constraints(script)  # This is deterministic, run it for real
    return {
        "agents": {
            "fact_checker": {"agent": "fact_checker", "passed": True, "issues": [], "raw": "VERDICT: PASS\nISSUES:\n- None"},
            "vibe_checker": {"agent": "vibe_checker", "passed": True, "score": 8, "feedback": ["Good conversational flow"], "raw": "VIBE_SCORE: 8\nVERDICT: PASS"},
            "engineering_constraints": eng,
        },
        "all_passed": eng["passed"],
        "combined_feedback": eng.get("issues", []),
    }


def run_review(
    script: str,
    research: dict,
    dry_run: bool = False,
) -> StepResult:
    """Execute the review panel. Returns StepResult with review data."""
    review = _run_review_panel(script, research, dry_run=dry_run)
    passed = review["all_passed"]

    # Build status message
    agent_statuses = []
    for name, result in review["agents"].items():
        status = "PASS" if result["passed"] else "FAIL"
        extra = ""
        if "score" in result:
            extra = f" (score: {result['score']})"
        agent_statuses.append(f"{name}: {status}{extra}")

    message = "Review panel: " + ", ".join(agent_statuses)
    return StepResult(output=review, passed=passed, message=message, attempt=1)
