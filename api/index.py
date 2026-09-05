"""Vercel's thin entrypoint for the existing ResearchNavigator FastAPI app."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_SOURCE_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(API_SOURCE_ROOT))

from research_navigator.main import app  # noqa: E402

__all__ = ["app"]
