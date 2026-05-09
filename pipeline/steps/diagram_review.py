"""Step 6b: Diagram Review — validate diagram against research and script content."""

import json

from pipeline.llm import call_anthropic
from pipeline.quality import StepResult

REVIEW_SYSTEM = """\
You are an architecture diagram reviewer for a system design podcast. Your job is to validate \
that the diagram accurately represents the system being discussed.

You will receive:
1. The diagram JSON (nodes, edges, groups)
2. Research notes (architecture components, talking points)
3. A script excerpt

Evaluate the diagram on these criteria:
1. COMPLETENESS — Are all major components from the research/script represented?
2. ACCURACY — Do edge directions make sense (data flows correctly)?
3. CONNECTIONS — Are there missing critical connections between components?
4. TYPES — Are node types appropriate (e.g., Redis should be "cache", not "server")?
5. CLARITY — Is the diagram readable and not cluttered?
6. NO OVERLAP — Critical rule: node labels and edge labels must NOT visually overlap each other.
   - Groups should not have too many nodes in a single row (max 4 per row recommended).
   - Edge labels should be short (max 2-3 words) to avoid overlapping adjacent nodes or other labels.
   - If nodes are too close together given their label lengths, flag it.
   - Long node labels (>16 chars) risk overlapping — suggest shorter alternatives.

Return your review as a JSON object:
{
  "passed": true/false,
  "score": 1-10,
  "issues": ["list of specific issues found"],
  "suggestions": ["list of improvements"],
  "missing_components": ["components from research not in diagram"],
  "summary": "one-line verdict"
}

Return ONLY valid JSON. No markdown fences, no extra text.
Be strict but fair — minor omissions are OK, but missing core components or wrong data flows are not.
A score of 7+ means PASS.
"""

REVIEW_PROMPT = """\
Review this architecture diagram for accuracy and completeness.

DIAGRAM JSON:
{diagram_json}

RESEARCH NOTES:
{research_json}

SCRIPT EXCERPT:
{script_excerpt}

Evaluate and return your review as JSON.
"""


def _parse_review(raw: str) -> dict:
    """Parse the LLM review response."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n", 1)
        raw = lines[1] if len(lines) > 1 else ""
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()
    return json.loads(raw)


def run_diagram_review(
    diagram_data: dict,
    research: dict,
    script: str,
    dry_run: bool = False,
) -> StepResult:
    """Review the diagram JSON against research and script.

    Returns StepResult with output=review_dict, passed based on score >= 7.
    """
    if dry_run:
        review = {
            "passed": True,
            "score": 9,
            "issues": [],
            "suggestions": ["Consider adding monitoring connections"],
            "missing_components": [],
            "summary": "Dry-run: diagram looks great",
        }
        return StepResult(output=review, passed=True, message="Dry-run: auto-pass", attempt=1)

    script_excerpt = " ".join(script.split()[:500])
    prompt = REVIEW_PROMPT.format(
        diagram_json=json.dumps(diagram_data, indent=2),
        research_json=json.dumps(research, indent=2),
        script_excerpt=script_excerpt,
    )

    raw = call_anthropic(prompt, system=REVIEW_SYSTEM, temperature=0.2)

    try:
        review = _parse_review(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return StepResult(
            output={"error": str(exc), "raw": raw[:500]},
            passed=False,
            message=f"Failed to parse review response: {exc}",
            attempt=1,
        )

    score = review.get("score", 0)
    passed = score >= 7
    issues = review.get("issues", [])
    summary = review.get("summary", f"Score: {score}/10")

    if not passed and issues:
        feedback = "; ".join(issues[:5])
        message = f"Score {score}/10 — {feedback}"
    else:
        message = f"Score {score}/10 — {summary}"

    return StepResult(output=review, passed=passed, message=message, attempt=1)
