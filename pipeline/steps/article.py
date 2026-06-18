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

# Chinese article quality gates (character-based, not word-based)
ARTICLE_ZH_CHAR_MIN = 1500
ARTICLE_ZH_CHAR_MAX = 4800
ARTICLE_ZH_MIN_HEADINGS = 4

ARTICLE_ZH_SYSTEM = """\
你是一名资深后端工程师和技术作者。你的任务是将一篇英文系统设计学习指南翻译成中文。\
语气要像资深工程师在跟同事聊技术问题——不是学生教程。

规则：
- 保留原文的结构、标题层级、表格、blockquote、项目符号、加粗等所有 markdown 格式。
- 技术术语保持英文：如 Token Bucket、Leaky Bucket、Redis、Snowflake、QPS、API、CDN、数据库产品名、公司名、\
  HTTP 状态码、各种算法名、专有名词、文件名等。
- 不要生硜的直译。调整句式使中文读起来自然，但保持原文的技术准确性和语气。
- 保留原文的意见和结论（"这里 Token Bucket 是最佳选择"这类表述不要转为中立）。
- 以 # 开头的标题使用中文；表格表头可以是中文。
- 不要加额外的译者注、前言或总结。只输出翻译后的文章本身。
- 不要使用 ### (h3)，只使用 # 和 ##。
"""

ARTICLE_ZH_PROMPT = """\
请将以下关于 "{topic}" 的英文系统设计学习指南翻译成中文。

英文原文：

{english_article}

---

辅助上下文（可以帮助选词，但不要加入原文中没有的内容）：
{research_summary}

输出要求：直接输出翻译后的 markdown 文章，不要任何额外说明。保留原文的结构和格式。
"""


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


def _generate_article_zh(topic: str, english_article: str, research: dict) -> str:
    """Call LLM to translate the article into Chinese markdown."""
    research_summary = _summarize_research(research)
    prompt = ARTICLE_ZH_PROMPT.format(
        topic=topic,
        english_article=english_article,
        research_summary=research_summary,
    )
    result = call_anthropic(prompt, system=ARTICLE_ZH_SYSTEM, max_tokens=4096, temperature=0.5)
    result = result.strip()
    if result.startswith("```"):
        result = re.sub(r"^```\w*\n?", "", result)
        result = re.sub(r"\n?```$", "", result)
    return result.strip()


def _validate_article_zh(article: str) -> tuple[bool, str]:
    """Validate Chinese article meets quality gates (character-based)."""
    char_count = len(article)
    if char_count < ARTICLE_ZH_CHAR_MIN:
        return False, f"Too short: {char_count} chars (min {ARTICLE_ZH_CHAR_MIN})"
    if char_count > ARTICLE_ZH_CHAR_MAX:
        return False, f"Too long: {char_count} chars (max {ARTICLE_ZH_CHAR_MAX})"

    headings = re.findall(r"^#{1,2}\s+.+", article, re.MULTILINE)
    if len(headings) < ARTICLE_ZH_MIN_HEADINGS:
        return False, f"Too few headings: {len(headings)} (min {ARTICLE_ZH_MIN_HEADINGS})"

    non_heading_lines = [l for l in article.split("\n") if l.strip() and not l.strip().startswith("#")]
    if len(non_heading_lines) < 10:
        return False, f"Too few content lines: {len(non_heading_lines)}"

    # Sanity check: must contain CJK characters
    cjk_count = sum(1 for c in article if "\u4e00" <= c <= "\u9fff")
    if cjk_count < 500:
        return False, f"Too few Chinese characters: {cjk_count} (min 500)"

    return True, f"Chinese article OK: {char_count} chars, {len(headings)} sections, {cjk_count} CJK chars"


def run_article_zh(
    topic: str,
    english_article: str,
    research: dict,
    dry_run: bool = False,
) -> StepResult:
    """Generate a Chinese version of the study guide article (translated from English).

    Args:
        topic: Episode topic name
        english_article: The English article markdown (from article.md)
        research: Research data dict (used as auxiliary context)
        dry_run: If True, return mock data

    Returns:
        StepResult with output=Chinese article markdown string
    """
    if dry_run:
        mock = (
            "# 限流器：学习指南\n\n"
            "## 为什么需要限流\n\n"
            "限流可以保护共享资源不被滥用。这是大规模系统中不可或缺的一环。使用 Token Bucket 算法是最常见的选择。\n\n"
            "## 四种算法\n\n"
            "Token Bucket、Leaky Bucket、Fixed Window、Sliding Window 各有优劣。选择依赖于你的业务需求。\n\n"
            "## 面试框架\n\n"
            "先明确需求，再谈扩展，最后深入分布式问题。这是职业面试官愿意看到的思路。\n\n"
            "## 分布式难题\n\n"
            "多节点协调是真正的挑战。Redis 是业界事实上的默认选择。\n\n"
            "## 关键要点\n\n"
            "1. 算法选择看突发容忍度\n2. 分布式协调是难点\n3. 实践中要面对时钟偏差问题\n"
        )
        return StepResult(output=mock, passed=True, message="Dry-run: mock zh article", attempt=1)

    result = run_with_quality_gate(
        step_fn=lambda: _generate_article_zh(topic, english_article, research),
        validate_fn=_validate_article_zh,
        max_retries=3,
    )
    return result
