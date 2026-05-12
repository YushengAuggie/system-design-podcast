from __future__ import annotations

"""Step 6: Diagram Generation — produce interactive HTML architecture diagrams."""

import json
import re
from pathlib import Path

from pipeline.config import DIAGRAM_MAX_RETRIES
from pipeline.llm import call_anthropic
from pipeline.quality import StepResult

DIAGRAM_SYSTEM = """\
You are a system architecture diagram generator. Given research notes and a podcast script, \
generate a structured JSON object describing the architecture diagram.

You MUST return ONLY valid JSON (no markdown fences, no explanation, no text before/after).

The JSON schema:
{
  "title": "string — title for the diagram",
  "nodes": [
    {
      "id": "string — unique lowercase identifier",
      "label": "string — display name",
      "type": "string — one of: client, server, database, cache, queue, service, storage, external, monitoring",
      "description": "string — 1-2 sentence description of this component's role"
    }
  ],
  "edges": [
    {
      "from": "string — source node id",
      "to": "string — target node id",
      "label": "string (optional) — short label for the connection"
    }
  ],
  "groups": [
    {
      "label": "string — group name",
      "nodeIds": ["string — node ids belonging to this group"]
    }
  ]
}

Rules:
- Include 6-15 nodes covering the key architecture components
- Use appropriate node types for color coding
- Show meaningful data flow directions with edges
- Group related components (e.g., "Data Layer", "Application Layer")
- Edge labels should be concise (e.g., "HTTPS", "gRPC", "Pub/Sub")
- Node IDs should be lowercase, no spaces (e.g., "load_balancer", "redis_cache")
- Return ONLY the JSON object, nothing else
"""

DIAGRAM_PROMPT = """\
Generate a structured JSON architecture diagram for this system design topic.

RESEARCH NOTES:
{research_json}

SCRIPT EXCERPT (for context):
{script_excerpt}

Generate a complete, accurate architecture diagram as a JSON object.
Return ONLY the JSON — no markdown fences, no explanation.
"""

# Path to the HTML template
TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "diagram-template.html"


def _parse_diagram_json(raw: str) -> dict:
    """Parse and clean LLM output into diagram JSON."""
    raw = raw.strip()
    # Strip markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()
    return json.loads(raw)


def _validate_diagram_json(data: dict) -> tuple[bool, str]:
    """Validate the diagram JSON structure."""
    if not isinstance(data, dict):
        return False, "Root must be a JSON object"

    if "nodes" not in data or not isinstance(data["nodes"], list):
        return False, "Missing or invalid 'nodes' array"

    if "edges" not in data or not isinstance(data["edges"], list):
        return False, "Missing or invalid 'edges' array"

    if len(data["nodes"]) < 3:
        return False, f"Too few nodes: {len(data['nodes'])} (need at least 3)"

    if len(data["edges"]) < 2:
        return False, f"Too few edges: {len(data['edges'])} (need at least 2)"

    # Check node structure
    node_ids = set()
    valid_types = {"client", "server", "database", "cache", "queue", "service", "storage", "external", "monitoring"}
    for node in data["nodes"]:
        if not isinstance(node, dict):
            return False, "Each node must be an object"
        for key in ("id", "label", "type"):
            if key not in node:
                return False, f"Node missing required field: '{key}'"
        if node["type"] not in valid_types:
            return False, f"Invalid node type '{node['type']}' for node '{node['id']}'. Valid types: {valid_types}"
        node_ids.add(node["id"])

    # Check edges reference valid nodes
    for edge in data["edges"]:
        if not isinstance(edge, dict):
            return False, "Each edge must be an object"
        if "from" not in edge or "to" not in edge:
            return False, "Edge missing 'from' or 'to'"
        if edge["from"] not in node_ids:
            return False, f"Edge references unknown node: '{edge['from']}'"
        if edge["to"] not in node_ids:
            return False, f"Edge references unknown node: '{edge['to']}'"

    # Check groups if present
    for group in data.get("groups", []):
        if not isinstance(group, dict):
            return False, "Each group must be an object"
        if "label" not in group or "nodeIds" not in group:
            return False, "Group missing 'label' or 'nodeIds'"
        for nid in group["nodeIds"]:
            if nid not in node_ids:
                return False, f"Group '{group['label']}' references unknown node: '{nid}'"

    return True, f"Valid diagram: {len(data['nodes'])} nodes, {len(data['edges'])} edges"


def _json_to_mermaid(data: dict) -> str:
    """Convert diagram JSON to Mermaid syntax for backward compatibility."""
    lines = ["graph TD"]

    # Node type shapes
    shape_map = {
        "client": ("[{label}]", ""),
        "server": ("[{label}]", ""),
        "database": ("[({label})]", ""),
        "cache": (">{label}]", "["),
        "queue": ("[/{label}/]", ""),
        "service": ("[{label}]", ""),
        "storage": ("[({label})]", ""),
        "external": ("({label})", ""),
        "monitoring": ("{{{{label}}}}", ""),
    }

    for node in data.get("nodes", []):
        nid = node["id"]
        label = node["label"]
        ntype = node.get("type", "service")
        shape_end, shape_start = shape_map.get(ntype, (f"[{label}]", ""))

        if shape_start:
            lines.append(f"    {nid}{shape_start}{shape_end.format(label=label)}")
        else:
            lines.append(f"    {nid}{shape_end.format(label=label)}")

    lines.append("")

    for edge in data.get("edges", []):
        label = edge.get("label", "")
        if label:
            lines.append(f"    {edge['from']} -->|{label}| {edge['to']}")
        else:
            lines.append(f"    {edge['from']} --> {edge['to']}")

    # Subgraphs for groups
    for group in data.get("groups", []):
        lines.append("")
        lines.append(f"    subgraph {group['label']}")
        for nid in group["nodeIds"]:
            lines.append(f"        {nid}")
        lines.append("    end")

    return "\n".join(lines)


def _render_html(data: dict) -> str:
    """Render the diagram JSON into the interactive HTML template."""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Diagram template not found: {TEMPLATE_PATH}")

    template = TEMPLATE_PATH.read_text()
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    return template.replace("{{DIAGRAM_DATA}}", json_str)


def _mock_diagram(research: dict) -> dict:
    """Return mock diagram JSON for dry-run mode."""
    topic = research.get("topic", "System")
    components = research.get("architecture_components", ["Client", "Server", "Database"])

    type_guesses = {
        "client": "client", "browser": "client", "mobile": "client",
        "load balancer": "server", "web": "server", "api": "server", "application": "server",
        "database": "database", "db": "database", "primary": "database",
        "cache": "cache", "redis": "cache", "memcached": "cache",
        "queue": "queue", "kafka": "queue", "message": "queue",
        "cdn": "external", "monitoring": "monitoring", "logging": "monitoring",
        "storage": "storage", "s3": "storage",
    }

    nodes = []
    for i, comp in enumerate(components[:10]):
        nid = f"n{i}"
        comp_lower = comp.lower()
        ntype = "service"
        for key, val in type_guesses.items():
            if key in comp_lower:
                ntype = val
                break
        nodes.append({
            "id": nid,
            "label": comp,
            "type": ntype,
            "description": f"{comp} component in the {topic} architecture",
        })

    edges = []
    for i in range(len(nodes) - 1):
        edges.append({"from": nodes[i]["id"], "to": nodes[i + 1]["id"]})

    return {
        "title": f"{topic} Architecture",
        "nodes": nodes,
        "edges": edges,
        "groups": [],
    }


def run_diagram(
    research: dict,
    script: str,
    dry_run: bool = False,
    max_retries: int = DIAGRAM_MAX_RETRIES,
    ep_dir: Path | None = None,
) -> StepResult:
    """Execute the diagram generation step.

    Produces:
    - diagram.json (structured data)
    - diagram.html (interactive visualization)
    - diagram.mmd (Mermaid for backward compat)

    Returns StepResult with output=diagram_data dict.
    """
    if dry_run:
        diagram_data = _mock_diagram(research)
        passed, message = _validate_diagram_json(diagram_data)
        return StepResult(output=diagram_data, passed=passed, message=message, attempt=1)

    last_error: str = ""
    diagram_data: dict = {}

    for attempt in range(1, max_retries + 1):
        extra_feedback = ""
        if last_error:
            extra_feedback = f"\n\nPrevious attempt failed: {last_error}. Please fix the issues."

        script_excerpt = " ".join(script.split()[:500])
        prompt = DIAGRAM_PROMPT.format(
            research_json=json.dumps(research, indent=2),
            script_excerpt=script_excerpt,
        ) + extra_feedback

        raw = call_anthropic(prompt, system=DIAGRAM_SYSTEM, temperature=0.3)

        try:
            diagram_data = _parse_diagram_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            msg = f"JSON parse error: {exc}"
            print(f"  Diagram parse failed (attempt {attempt}/{max_retries}): {msg}")
            last_error = msg
            continue

        passed, message = _validate_diagram_json(diagram_data)
        if passed:
            return StepResult(output=diagram_data, passed=True, message=message, attempt=attempt)

        print(f"  Diagram validation failed (attempt {attempt}/{max_retries}): {message}")
        last_error = message

    return StepResult(output=diagram_data, passed=False, message=last_error, attempt=max_retries)
