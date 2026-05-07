"""Entry point for `python -m pipeline`."""

from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (don't override existing env vars)
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

from pipeline.main import cli

cli()
