"""Entry point for `python -m pipeline`."""

from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from pipeline.main import cli

cli()
