"""Step 6c: Screenshot — render diagram.html to PNG via Playwright."""

from __future__ import annotations


import shutil
from pathlib import Path

from pipeline.config import DIAGRAM_SCREENSHOT_HEIGHT, DIAGRAM_SCREENSHOT_WIDTH
from pipeline.quality import StepResult


def _has_playwright() -> bool:
    """Check if Playwright is importable and Chromium is likely installed."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def run_screenshot(
    html_path: Path,
    output_path: Path,
    width: int = DIAGRAM_SCREENSHOT_WIDTH,
    height: int = DIAGRAM_SCREENSHOT_HEIGHT,
    dry_run: bool = False,
) -> StepResult:
    """Render diagram.html to a PNG screenshot.

    Args:
        html_path: Path to the diagram HTML file.
        output_path: Where to save the PNG.
        width: Viewport width.
        height: Viewport height.
        dry_run: If True, skip actual rendering.

    Returns:
        StepResult with output=output_path on success.
    """
    if dry_run:
        return StepResult(
            output=str(output_path),
            passed=True,
            message="Dry-run: screenshot skipped",
            attempt=1,
        )

    if not html_path.exists():
        return StepResult(
            output=None,
            passed=False,
            message=f"HTML file not found: {html_path}",
            attempt=1,
        )

    if not _has_playwright():
        return StepResult(
            output=None,
            passed=False,
            message="Playwright not installed. Run: pip install playwright && playwright install chromium",
            attempt=1,
        )

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})

            # Load the file
            file_url = f"file://{html_path.resolve()}"
            page.goto(file_url, wait_until="networkidle")

            # Give JS a moment to render
            page.wait_for_timeout(1000)

            # Screenshot
            page.screenshot(path=str(output_path), full_page=False)
            browser.close()

        if not output_path.exists() or output_path.stat().st_size < 1000:
            return StepResult(
                output=None,
                passed=False,
                message=f"Screenshot file too small or missing: {output_path}",
                attempt=1,
            )

        size_kb = output_path.stat().st_size // 1024
        return StepResult(
            output=str(output_path),
            passed=True,
            message=f"Screenshot saved: {output_path.name} ({size_kb} KB)",
            attempt=1,
        )

    except Exception as exc:
        return StepResult(
            output=None,
            passed=False,
            message=f"Screenshot failed: {exc}",
            attempt=1,
        )
