"""Tests for the Jira issue field list. Runnable with pytest or directly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.commands.jira_get import issue_fields  # noqa: E402


def test_default_fields_omit_comments():
    assert issue_fields(None, False) == "*navigable"


def test_comments_are_requested_explicitly():
    assert issue_fields(None, True) == "*navigable,comment"


def test_comments_appended_to_requested_fields():
    assert issue_fields("summary,status", True) == "summary,status,comment"


def test_comment_field_is_not_duplicated():
    assert issue_fields("comment,summary", True) == "comment,summary"


def test_configured_custom_fields_are_appended():
    assert issue_fields(None, True, ["customfield_10016", "", None]) == (
        "*navigable,comment,customfield_10016"
    )


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
