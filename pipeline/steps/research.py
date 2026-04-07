"""Step 1: Research — gather talking points and real-world references for a topic."""

import json

from pipeline.config import RESEARCH_MIN_REFERENCES, RESEARCH_MIN_TALKING_POINTS
from pipeline.llm import call_anthropic
from pipeline.quality import StepResult, run_with_quality_gate

RESEARCH_SYSTEM = """\
You are a senior systems engineer and podcast researcher. Your job is to produce \
structured research notes for a system design podcast episode.

Return ONLY valid JSON (no markdown fences) with this exact schema:
{
  "topic": "string",
  "season": int,
  "episode": int,
  "summary": "1-2 sentence overview",
  "talking_points": ["point1", "point2", ...],  // at least 5
  "real_world_references": [
    {"company": "string", "detail": "string", "url": "string (eng blog or docs URL)"}
  ],  // at least 3 distinct companies
  "interview_angles": ["angle1", "angle2", ...],
  "common_mistakes": ["mistake1", "mistake2", ...],
  "architecture_components": ["component1", "component2", ...]
}
"""

RESEARCH_PROMPT = """\
Research the following system design topic for a podcast episode.

Topic: {topic}
Season: {season}
Episode: {episode}

Provide comprehensive research notes including:
- At least 5 key talking points covering design challenges, trade-offs, and scaling strategies
- At least 3 real company references with engineering blog URLs (e.g., from company tech blogs, \
InfoQ, High Scalability, etc.)
- Interview angles: how this topic appears in system design interviews
- Common mistakes candidates make when discussing this topic
- Key architecture components that should appear in a diagram

Focus on accuracy. Only cite real engineering blog posts and real company practices.
"""


def _generate_research(topic: str, season: int, episode: int) -> dict:
    """Call LLM to generate research notes."""
    prompt = RESEARCH_PROMPT.format(topic=topic, season=season, episode=episode)
    raw = call_anthropic(prompt, system=RESEARCH_SYSTEM)
    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw.strip())


def _validate_research(data: dict) -> tuple[bool, str]:
    """Validate research meets quality gates."""
    issues: list[str] = []

    talking_points = data.get("talking_points", [])
    if len(talking_points) < RESEARCH_MIN_TALKING_POINTS:
        issues.append(
            f"Need >= {RESEARCH_MIN_TALKING_POINTS} talking points, got {len(talking_points)}"
        )

    refs = data.get("real_world_references", [])
    companies = {r.get("company", "").lower() for r in refs}
    if len(companies) < RESEARCH_MIN_REFERENCES:
        issues.append(
            f"Need >= {RESEARCH_MIN_REFERENCES} distinct company references, got {len(companies)}"
        )

    if issues:
        return False, "; ".join(issues)
    return True, "Research quality gates passed"


def _mock_research(topic: str, season: int, episode: int) -> dict:
    """Return mock research data for dry-run mode."""
    return {
        "topic": topic,
        "season": season,
        "episode": episode,
        "summary": f"A deep dive into {topic} covering architecture, scaling, and real-world usage.",
        "talking_points": [
            "Core architecture overview",
            "Scaling challenges and solutions",
            "Data model and storage choices",
            "Consistency vs availability trade-offs",
            "Performance optimization techniques",
        ],
        "real_world_references": [
            {
                "company": "Google",
                "detail": f"Google's approach to {topic}",
                "url": "https://research.google/blog/example",
            },
            {
                "company": "Netflix",
                "detail": f"Netflix's {topic} at scale",
                "url": "https://netflixtechblog.com/example",
            },
            {
                "company": "Uber",
                "detail": f"Uber's {topic} architecture",
                "url": "https://www.uber.com/blog/example",
            },
        ],
        "interview_angles": [
            "Start with requirements gathering",
            "Discuss trade-offs explicitly",
        ],
        "common_mistakes": [
            "Jumping to solutions without clarifying requirements",
            "Ignoring failure modes",
        ],
        "architecture_components": [
            "Load Balancer",
            "Application Server",
            "Database",
            "Cache",
            "Message Queue",
        ],
    }


def run_research(
    topic: str, season: int, episode: int, dry_run: bool = False
) -> StepResult:
    """Execute the research step with quality gates."""
    if dry_run:
        data = _mock_research(topic, season, episode)
        passed, msg = _validate_research(data)
        return StepResult(output=data, passed=passed, message=msg, attempt=1)

    return run_with_quality_gate(
        step_fn=_generate_research,
        validate_fn=_validate_research,
        max_retries=3,
        topic=topic,
        season=season,
        episode=episode,
    )
