"""Tests for Jira issue fields and comment output. Runnable with pytest or directly."""

import io
import json
import sys
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.commands import jira_get  # noqa: E402
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


def _get_issue(fields, *, comments, json_output):
    client = Mock()
    client.jira_get.return_value = {"key": "DEMO-1", "id": "101", "fields": fields}
    args = Namespace(key="DEMO-1", fields="summary", comments=comments, json=json_output)
    with (
        patch.object(jira_get, "get_story_points_field", return_value=None),
        patch.object(jira_get, "get_acceptance_criteria_field", return_value=None),
        redirect_stdout(io.StringIO()) as output,
    ):
        jira_get.run(args, client)
    requested = "summary,comment" if comments else "summary"
    client.jira_get.assert_called_once_with("issue/DEMO-1", params={"fields": requested})
    return output.getvalue()


def test_comment_counts_distinguish_partial_complete_empty_and_unknown_results():
    comment = {
        "id": "201",
        "author": {"displayName": "Demo User"},
        "body": {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Demo comment"}]},
        ]},
    }
    cases = [
        ({"comments": [comment], "total": 3}, 1, 3, True, "1 of 3 shown"),
        ({"comments": [comment], "total": 1}, 1, 1, False, "1 of 1 shown"),
        ({"comments": [], "total": 0}, 0, 0, False, "0 of 0 shown"),
        ({"comments": [comment]}, 1, None, None, "1 shown, total unknown"),
        (None, 0, None, None, "0 shown, total unknown"),
    ]
    for comment_page, returned, total, has_more, heading in cases:
        fields = {"summary": "Demo issue", "comment": comment_page}
        markdown = _get_issue(fields, comments=True, json_output=False)
        assert f"### Comments ({heading})" in markdown
        if returned:
            assert "Demo comment" in markdown
        result = json.loads(_get_issue(fields, comments=True, json_output=True))
        assert result == {
            "schema_version": 1, "key": "DEMO-1", "id": "101", "fields": fields,
            "comments_pagination": {"returned": returned, "total": total, "has_more": has_more},
        }


def test_default_get_does_not_add_comment_metadata():
    fields = {"summary": "Demo issue"}
    assert "### Comments" not in _get_issue(fields, comments=False, json_output=False)
    assert json.loads(_get_issue(fields, comments=False, json_output=True)) == {
        "schema_version": 1, "key": "DEMO-1", "id": "101", "fields": fields,
    }


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
