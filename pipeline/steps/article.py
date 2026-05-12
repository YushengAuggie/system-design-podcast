from __future__ import annotations

"""Pipeline step: Generate a study guide article from the finalized script and research."""

import re

from pipeline.llm import call_anthropic
from pipeline.quality import StepResult, run_with_quality_gate

ARTICLE_SYSTEM = """\
You are a senior engineer and technical writer. Your job is to write a concise, \
readable study guide article for a system design topic. Think Stripe's engineering blog \
or Cloudflare's blog — knowledgeable, concise, conversational.

Rules:
- 800-1500 words total
- Use markdown formatting: ## headings, **bold**, bullet lists, tables (pipe syntax)
- Tone: senior engineer explaining to a peer. NOT a beginner tutorial.
- Include: what it is & why it matters, key algorithms/approaches with trade-offs, \
  interview framework, distributed challenges, real-world implementations, key takeaways
- Use comparison tables where appropriate
- Include > blockquotes for key insights
- Be opinionated — state which approach is best for common cases
- Do NOT use ### (h3) — only # (h1 for title) and ## (h2 for sections)
- Start with a # title, then dive right in
"""

ARTICLE_PROMPT = """\
Write a study guide article for the following system design topic.

Topic: {topic}

Research data (key points, references, architecture components):
{research_summary}

Podcast script (for context on what was discussed):
{script_excerpt}

Write the article in markdown. Make it standalone — someone should be able to read \
this without listening to the podcast and still get full value. Focus on practical \
knowledge that's useful in interviews and real system design.
"""

# --- Quality gates ---
ARTICLE_WORD_MIN = 800
ARTICLE_WORD_MAX = 1500
ARTICLE_MIN_HEADINGS = 4


def _summarize_research(research: dict) -> str:
    """Build a concise research summary for the prompt."""
    parts = []
    if research.get("talking_points"):
        parts.append("Talking points:\n" + "\n".join(f"- {p}" for p in research["talking_points"]))
    if research.get("real_world_references"):
        refs = research["real_world_references"]
        parts.append("References:\n" + "\n".join(f"- {r['company']}: {r['detail']}" for r in refs))
    if research.get("architecture_components"):
        parts.append("Components: " + ", ".join(research["architecture_components"]))
    if research.get("common_mistakes"):
        parts.append("Common mistakes:\n" + "\n".join(f"- {m}" for m in research["common_mistakes"][:5]))
    return "\n\n".join(parts)


def _generate_article(topic: str, research: dict, script_text: str) -> str:
    """Call LLM to generate the article markdown."""
    research_summary = _summarize_research(research)
    # Use first ~2000 chars of script for context
    script_excerpt = script_text[:2000] + ("..." if len(script_text) > 2000 else "")

    prompt = ARTICLE_PROMPT.format(
        topic=topic,
        research_summary=research_summary,
        script_excerpt=script_excerpt,
    )

    result = call_anthropic(prompt, system=ARTICLE_SYSTEM, max_tokens=4096, temperature=0.7)
    # Strip markdown fences if present
    result = result.strip()
    if result.startswith("```"):
        result = re.sub(r"^```\w*\n?", "", result)
        result = re.sub(r"\n?```$", "", result)
    return result.strip()


def _validate_article(article: str) -> tuple[bool, str]:
    """Validate article meets quality gates."""
    word_count = len(article.split())
    if word_count < ARTICLE_WORD_MIN:
        return False, f"Too short: {word_count} words (min {ARTICLE_WORD_MIN})"
    if word_count > ARTICLE_WORD_MAX:
        return False, f"Too long: {word_count} words (max {ARTICLE_WORD_MAX})"

    # Check for headings
    headings = re.findall(r"^#{1,2}\s+.+", article, re.MULTILINE)
    if len(headings) < ARTICLE_MIN_HEADINGS:
        return False, f"Too few headings: {len(headings)} (min {ARTICLE_MIN_HEADINGS})"

    # Check it has actual content (not just headings)
    non_heading_lines = [l for l in article.split("\n") if l.strip() and not l.strip().startswith("#")]
    if len(non_heading_lines) < 20:
        return False, f"Too few content lines: {len(non_heading_lines)}"

    return True, f"Article OK: {word_count} words, {len(headings)} sections"


def run_article(
    topic: str,
    research: dict,
    script_text: str,
    dry_run: bool = False,
) -> StepResult:
    """Generate a study guide article for an episode.

    Args:
        topic: Episode topic name
        research: Research data dict
        script_text: The finalized script text
        dry_run: If True, return mock data

    Returns:
        StepResult with output=article markdown string
    """
    if dry_run:
        mock = (
            "# Rate Limiter: Study Guide\n\n"
            "## Why Rate Limiting Matters\n\n"
            "Rate limiting protects shared resources from overuse...\n\n"
            "## The Four Algorithms\n\n"
            "Token Bucket, Leaky Bucket, Fixed Window, Sliding Window...\n\n"
            "## The Interview Framework\n\n"
            "Start with requirements, then scale, then deep dive...\n\n"
            "## The Distributed Problem\n\n"
            "Coordination across servers is the real challenge...\n\n"
            "## Key Takeaways\n\n"
            "1. Algorithm choice depends on burst tolerance\n"
            "2. Distributed coordination is the hard part\n"
        )
        return StepResult(output=mock, passed=True, message="Dry-run: mock article", attempt=1)

    result = run_with_quality_gate(
        step_fn=lambda: _generate_article(topic, research, script_text),
        validate_fn=_validate_article,
        max_retries=3,
    )
    return result
