"""Step 6: Diagram Generation — produce a Mermaid architecture diagram."""

import re

from pipeline.llm import call_anthropic
from pipeline.quality import StepResult

DIAGRAM_SYSTEM = """\
You are a system architecture diagram generator. Given research notes and a podcast script, \
generate a clear Mermaid diagram that shows the key architecture components and their relationships.

Rules:
- Use Mermaid graph TD (top-down) or LR (left-right) syntax
- Include the key components mentioned in the discussion
- Show data flow directions with arrows
- Keep it readable — no more than 15 nodes
- Return ONLY the Mermaid code, no markdown fences, no explanation
"""

DIAGRAM_PROMPT = """\
Generate a Mermaid architecture diagram for this system design topic.

RESEARCH NOTES:
{research_json}

SCRIPT EXCERPT (for context):
{script_excerpt}

Generate a clear, readable Mermaid diagram showing the high-level architecture.
Return ONLY the Mermaid code.
"""


def _generate_diagram(research: dict, script: str) -> str:
    """Call LLM to generate Mermaid diagram code."""
    import json

    # Use first ~500 words of script for context
    script_excerpt = " ".join(script.split()[:500])
    prompt = DIAGRAM_PROMPT.format(
        research_json=json.dumps(research, indent=2),
        script_excerpt=script_excerpt,
    )
    raw = call_anthropic(prompt, system=DIAGRAM_SYSTEM, temperature=0.3)
    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


def _validate_diagram(mermaid_code: str) -> tuple[bool, str]:
    """Basic validation of Mermaid syntax."""
    if not mermaid_code.strip():
        return False, "Empty diagram"

    # Check for basic Mermaid graph declaration
    has_graph = bool(re.search(r"^(graph|flowchart|sequenceDiagram|classDiagram)", mermaid_code, re.MULTILINE))
    if not has_graph:
        return False, "Missing Mermaid graph declaration (graph/flowchart/etc)"

    # Check for at least some nodes/edges
    has_arrows = "-->" in mermaid_code or "---" in mermaid_code or "-.->"\
        in mermaid_code
    if not has_arrows:
        return False, "No edges/arrows found in diagram"

    lines = [l.strip() for l in mermaid_code.split("\n") if l.strip()]
    if len(lines) < 3:
        return False, f"Diagram too simple: only {len(lines)} lines"

    return True, "Valid Mermaid diagram"


def _mock_diagram(research: dict) -> str:
    """Return mock Mermaid diagram for dry-run mode."""
    topic = research.get("topic", "System")
    components = research.get("architecture_components", ["Client", "Server", "Database"])
    lines = ["graph TD"]
    for i, comp in enumerate(components):
        node_id = f"N{i}"
        lines.append(f"    {node_id}[{comp}]")
    # Chain them together
    for i in range(len(components) - 1):
        lines.append(f"    N{i} --> N{i + 1}")
    return "\n".join(lines)


def run_diagram(
    research: dict,
    script: str,
    dry_run: bool = False,
    max_retries: int = 2,
) -> StepResult:
    """Execute the diagram generation step with quality gates and retry."""
    if dry_run:
        mermaid_code = _mock_diagram(research)
        passed, message = _validate_diagram(mermaid_code)
        return StepResult(output=mermaid_code, passed=passed, message=message, attempt=1)

    last_error: str = ""
    for attempt in range(1, max_retries + 1):
        import json

        # On retry, inject feedback about what was wrong into the prompt
        extra_feedback = ""
        if last_error:
            extra_feedback = f"\n\nPrevious attempt failed validation: {last_error}. Please fix the Mermaid syntax."

        script_excerpt = " ".join(script.split()[:500])
        prompt = DIAGRAM_PROMPT.format(
            research_json=json.dumps(research, indent=2),
            script_excerpt=script_excerpt,
        ) + extra_feedback

        raw = call_anthropic(prompt, system=DIAGRAM_SYSTEM, temperature=0.3)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        mermaid_code = raw.strip()

        passed, message = _validate_diagram(mermaid_code)
        if passed:
            return StepResult(output=mermaid_code, passed=True, message=message, attempt=attempt)

        print(f"  Diagram validation failed (attempt {attempt}/{max_retries}): {message}")
        last_error = message

    return StepResult(output=mermaid_code, passed=False, message=message, attempt=max_retries)
