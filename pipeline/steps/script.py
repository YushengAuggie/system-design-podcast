"""Step 2: Script Generation — produce a two-host conversational script."""

from pathlib import Path
from typing import Callable

from pipeline.config import (
    SCRIPT_MAX_RETRIES,
    SCRIPT_WORD_MAX,
    SCRIPT_WORD_MIN,
    SCRIPT_WORD_SOFT_MAX,
)
from pipeline.llm import call_anthropic
from pipeline.quality import StepResult, run_with_quality_gate
from pipeline.utils import word_count

TEMPLATE_PATH = Path("templates/episode-template.md")

SCRIPT_SYSTEM = """\
You are a podcast script writer for a system design podcast. You write natural, \
engaging two-host dialogue that sounds like two smart friends talking — NOT a textbook.

Rules:
- Follow the 5-segment template structure exactly
- Use **[Host A]:** and **[Host B]:** labels for every line of dialogue
- Host A leads and explains; Host B asks sharp questions, reacts, adds energy
- Include all 5 segments with --- dividers between them
- Keep the script between 750-1500 words of dialogue content
- Include a References section at the end with real URLs
- Be specific: use real numbers, real company names, real trade-offs
- Sound conversational: contractions, reactions ("Oh that's interesting"), natural flow
"""

SCRIPT_PROMPT = """\
Write a podcast episode script based on these research notes.

{research_json}

Follow this episode template structure:
{template}

Requirements:
- Topic: {topic} (Season {season}, Episode {episode})
- Word count target: 750-1500 words (dialogue content only)
- Include all 5 segments: The Problem, Interview Framework, Deep Dive, How They Actually Built It, Interview Tips
- Include a References section with real engineering blog URLs from the research
- Make it sound natural and engaging — two hosts having a real conversation
"""

REVISION_PROMPT = """\
Revise this podcast script based on the following feedback.

CURRENT SCRIPT:
{script}

FEEDBACK:
{feedback}

Keep the same 5-segment structure and Host A/Host B format. Address ALL feedback points.
Target word count: 750-1500 words of dialogue content.
"""


def _load_template() -> str:
    """Load the episode template."""
    return TEMPLATE_PATH.read_text()


def _generate_script(
    research: dict,
    topic: str,
    season: int,
    episode: int,
    feedback: str = "",
    previous_script: str = "",
) -> str:
    """Call LLM to generate or revise a script."""
    if feedback and previous_script:
        prompt = REVISION_PROMPT.format(script=previous_script, feedback=feedback)
    else:
        import json

        template = _load_template()
        prompt = SCRIPT_PROMPT.format(
            research_json=json.dumps(research, indent=2),
            template=template,
            topic=topic,
            season=season,
            episode=episode,
        )
    return call_anthropic(prompt, system=SCRIPT_SYSTEM)


def _validate_script(script: str) -> tuple[bool, str]:
    """Validate script word count."""
    wc = word_count(script)
    if wc < SCRIPT_WORD_MIN:
        return False, f"Script too short: {wc} words (min {SCRIPT_WORD_MIN})"
    if wc > SCRIPT_WORD_SOFT_MAX:
        return False, f"Script too long: {wc} words (soft max {SCRIPT_WORD_SOFT_MAX})"
    return True, f"Script word count OK: {wc} words"


def _make_feedback_fn(research: dict, topic: str, season: int, episode: int) -> Callable:
    """Create a closure that captures research/context for revision retries."""
    def _feedback_fn(output: str, message: str) -> dict:
        return {
            "research": research,
            "topic": topic,
            "season": season,
            "episode": episode,
            "feedback": message,
            "previous_script": output,
        }
    return _feedback_fn


def _mock_script(topic: str, season: int, episode: int) -> str:
    """Return a mock script for dry-run mode."""
    lines = [
        f"# Episode {episode}: {topic}\n",
        "## Metadata",
        f"- **Topic:** {topic}",
        f"- **Season:** {season}",
        "- **Target Length:** 5-10 minutes\n",
        "---\n",
        "## Segment 1: The Problem (~2 min)\n",
        f"**[Host A]:** Welcome back everyone! Today we're tackling {topic} — one of the most "
        "classic system design problems out there.\n",
        "**[Host B]:** Oh this is a good one. Everyone thinks it's simple until you start "
        "thinking about scale.\n",
        "**[Host A]:** Exactly. At its core, we need to handle millions of requests per second "
        "with low latency and high availability.\n",
        "---\n",
        "## Segment 2: Interview Framework (~3 min)\n",
        '**[Host A]:** So if you got this in an interview, where do you start?\n',
        "**[Host B]:** First things first — clarify requirements. What are the functional and "
        "non-functional requirements?\n",
        "**[Host A]:** For functional requirements we need the core operations. For "
        "non-functional, think about latency, throughput, and durability.\n",
        "**[Host B]:** Let's sketch the high-level architecture. We'll need a load balancer, "
        "application servers, a database layer, and probably a cache.\n",
        "---\n",
        "## Segment 3: Deep Dive (~3 min)\n",
        '**[Host A]:** Okay, now let\'s get into the hard parts.\n',
        "**[Host B]:** The biggest challenge here is handling the read-to-write ratio. Most "
        "systems like this are heavily read-biased.\n",
        "**[Host A]:** Right, and that's where caching becomes critical. But you have to think "
        "about cache invalidation — one of the two hard problems in computer science.\n",
        "**[Host B]:** And don't forget about data partitioning. As your data grows, you need a "
        "solid sharding strategy. Consistent hashing is your friend here.\n",
        "---\n",
        "## Segment 4: How They Actually Built It (~2 min)\n",
        f'**[Host A]:** So how do real companies handle {topic} in production?\n',
        "**[Host B]:** Google's approach is fascinating. They use a multi-tier architecture with "
        "aggressive caching at every level.\n",
        "**[Host A]:** Netflix does something similar but with a twist — they lean heavily into "
        "eventual consistency because for their use case, availability matters more than "
        "strict consistency.\n",
        "**[Host B]:** And Uber's approach is different again. They prioritize low latency above "
        "everything else because real-time matters for ride matching.\n",
        "---\n",
        "## Segment 5: Interview Tips (~1 min)\n",
        '**[Host A]:** Alright, rapid-fire interview tips.\n',
        "**[Host B]:** Number one: always start with requirements. Don't jump into the "
        "solution.\n",
        "**[Host A]:** Number two: discuss trade-offs explicitly. Interviewers love hearing you "
        "reason about consistency vs availability.\n",
        "**[Host B]:** And the key takeaway — there's no perfect design. It's all about "
        "making informed trade-offs for your specific use case.\n",
        "---\n",
        "## References",
        "- https://research.google/blog/example",
        "- https://netflixtechblog.com/example",
        "- https://www.uber.com/blog/example\n",
        "## Architecture Diagram",
        "Load Balancer -> Application Servers -> Cache -> Database",
    ]
    return "\n".join(lines)


def run_script(
    research: dict,
    topic: str,
    season: int,
    episode: int,
    dry_run: bool = False,
    review_feedback: str = "",
    previous_script: str = "",
) -> StepResult:
    """Execute the script generation step with quality gates.

    If review_feedback and previous_script are provided, this is a revision
    pass driven by the review panel (skips fresh generation).
    """
    if dry_run:
        script = _mock_script(topic, season, episode)
        passed, msg = _validate_script(script)
        return StepResult(output=script, passed=passed, message=msg, attempt=1)

    feedback_fn = _make_feedback_fn(research, topic, season, episode)
    return run_with_quality_gate(
        step_fn=_generate_script,
        validate_fn=_validate_script,
        max_retries=SCRIPT_MAX_RETRIES,
        feedback_fn=feedback_fn,
        research=research,
        topic=topic,
        season=season,
        episode=episode,
        feedback=review_feedback,
        previous_script=previous_script,
    )
