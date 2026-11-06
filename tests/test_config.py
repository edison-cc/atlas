"""Tests for optional Jira custom-field config. Runnable with pytest or directly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.config import (  # noqa: E402
    get_acceptance_criteria_field,
    get_story_points_field,
)


def test_story_points_unset():
    assert get_story_points_field({}) is None


def test_story_points_blank():
    assert get_story_points_field({"story_points_field": "  "}) is None


def test_story_points_configured():
    assert get_story_points_field({"story_points_field": "customfield_10016"}) == (
        "customfield_10016"
    )


def test_acceptance_criteria_unset():
    assert get_acceptance_criteria_field({}) is None


def test_acceptance_criteria_configured():
    assert get_acceptance_criteria_field(
        {"acceptance_criteria_field": "customfield_10046"}
    ) == "customfield_10046"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"[PASS] {name}")
            except AssertionError as e:
                failures += 1
                print(f"[FAIL] {name}: {e}")
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
