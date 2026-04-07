# Pipeline Build Task

Build a Python pipeline for generating system design podcast episodes. Read the existing README.md and templates/episode-template.md first to understand the project structure.

## Requirements

### Architecture
- Python 3.12, use a pyproject.toml with dependencies (openai, anthropic, pydantic, click)
- Main entry: `pipeline/main.py` — orchestrates the full pipeline
- Each pipeline step is its own module in `pipeline/steps/`
- Config in `pipeline/config.py` (voices, word limits, retry settings, API model names)

### Pipeline Steps (in order)

1. **Research** (`pipeline/steps/research.py`)
   - Input: topic name + season number + episode number
   - Uses LLM to gather key talking points, real-world references, engineering blog URLs
   - Output: structured research notes (JSON)
   - Quality gate: must have >= 3 real company references, >= 5 talking points

2. **Script Generation** (`pipeline/steps/script.py`)
   - Input: research notes + episode template
   - Uses LLM to generate a two-host conversational script following the template format
   - Output: script markdown file
   - Quality gate: word count 750-1500 words (soft upper limit — up to 1650 OK, but aim for range). If outside range, regenerate with feedback. Max 3 retries.

3. **Script Review — Three-Agent Panel** (`pipeline/steps/review.py`)
   - This is NOT a single reviewer. It's a panel of three specialized agents that each review the script independently, then their verdicts are combined.
   
   **Agent 1: Fact Checker**
   - Reviews all technical claims, system design statements, company references
   - Verifies that architecture descriptions are accurate
   - Flags any hallucinated or incorrect technical details
   - Output: list of issues (if any) + pass/fail
   
   **Agent 2: Vibe & Broadcast Quality**
   - Reviews for natural conversation flow and engagement
   - Checks word choice — should sound like two smart friends talking, not a textbook
   - Evaluates entertainment value, pacing, hooks, and energy
   - Checks that it would be attractive and engaging for a podcast audience
   - Output: vibe score (1-10) + specific feedback + pass/fail (must score >= 7)
   
   **Agent 3: Engineering Constraints**
   - Checks word count (750-1500, soft cap at 1650)
   - Checks segment balance (no segment too long/short relative to template guidelines)
   - Checks format compliance (proper Host A/Host B labels, all 5 segments present)
   - Checks that references section exists with real URLs
   - This agent uses DETERMINISTIC code checks where possible (word count, format regex), LLM only for subjective segment balance
   - Output: checklist results + pass/fail
   
   **Combined Verdict:**
   - All three must pass for the script to proceed
   - If any agent fails, collect ALL feedback from all three, send back to script generation for revision
   - Max 2 full review cycles (generate → review panel → revise → review panel)
   - Each review cycle runs all three agents in parallel (they're independent)

4. **Voice Selection** (`pipeline/steps/voices.py`)
   - Input: episode metadata (season, episode number)
   - Picks voice pair based on season defaults from README voice rotation table
   - With some randomness: 70% chance use season default, 30% chance random pair from the full pool
   - Output: (host_a_voice, host_b_voice)

5. **Audio Generation** (`pipeline/steps/audio.py`)
   - Input: approved script + voice pair
   - Parse script into individual lines with speaker labels
   - Call OpenAI TTS API (gpt-4o-mini-tts) for each line with appropriate voice
   - Concatenate audio segments into final episode MP3
   - Output: episode.mp3
   - Quality gate: audio file exists, duration 3-12 minutes (flexible upper bound)
   - Need pydub for audio concatenation (add to dependencies)

6. **Diagram Generation** (`pipeline/steps/diagram.py`)
   - Input: research notes + script
   - Uses LLM to generate Mermaid diagram code for the architecture
   - Output: diagram.mmd file (we'll render it separately)
   - Quality gate: valid mermaid syntax (basic check)

### Pipeline Runner (`pipeline/main.py`)
- Click CLI: `python -m pipeline generate --topic "URL Shortener" --season 1 --episode 1`
- Also: `python -m pipeline generate --topic "URL Shortener" --season 1 --episode 1 --step script` (run from a specific step, loading prior outputs)
- Each step saves its output to `episodes/XX-topic-slug/` (e.g., `episodes/01-url-shortener/research.json`, `script.md`, `review.json`, `episode.mp3`, `diagram.mmd`)
- If a step fails after max retries, stop pipeline and report which step failed and why
- Logging: print each step name, status, and quality gate results
- Dry-run mode: `--dry-run` skips API calls, uses mock data

### Quality Gate Pattern
Every step follows this pattern:
```python
class StepResult:
    output: Any
    passed: bool
    message: str
    attempt: int

def run_with_quality_gate(step_fn, validate_fn, max_retries, feedback_fn=None):
    # Run step, validate, retry with feedback if failed, up to max_retries
```

### Key Design Principles
- **Deterministic where possible** — word counts, file existence, duration checks are all code, not LLM
- **Soft limits** — we don't want to cut episodes. Exceeding word/time limits slightly is OK, but the pipeline should try to hit the target range
- **Each step is independently runnable** — can re-run just one step
- **All intermediate artifacts saved** — can inspect/debug any step's output
- **Three-agent review is the core quality mechanism** — this is where we catch problems before expensive audio generation

### Voice Config (from README)
Season defaults:
- Season 1: Ash + Nova
- Season 2: Echo + Coral  
- Season 3: Onyx + Shimmer
- Season 4: Sage + Fable

All available Host A voices: alloy, echo, onyx, ash, sage
All available Host B voices: nova, shimmer, fable, coral, ballad

### File Structure to Create
```
pipeline/
├── __init__.py
├── __main__.py          # Click CLI entry
├── main.py              # Pipeline orchestrator
├── config.py            # All config constants
├── quality.py           # Quality gate pattern
├── steps/
│   ├── __init__.py
│   ├── research.py
│   ├── script.py
│   ├── review.py        # Contains all three review agents + combined verdict logic
│   ├── voices.py
│   ├── audio.py
│   └── diagram.py
├── llm.py               # Shared LLM calling utility (supports both openai and anthropic)
└── utils.py             # Shared utilities (slugify, word count, file I/O)
pyproject.toml
```

DO NOT create a venv or install packages. Just write the code and pyproject.toml.

Make sure the code is clean, well-typed (use type hints), and each module has a clear docstring.
Use environment variables for API keys: OPENAI_API_KEY, ANTHROPIC_API_KEY.
Default LLM provider: anthropic/claude-sonnet-4-20250514 for script/research/review/diagram. OpenAI for TTS only.
