"""Stable paths for tests regardless of folder nesting."""

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
SAMPLE_REPO = FIXTURES_DIR / "sample-repo"
SKILLS_DIR = REPO_ROOT / "skills"
