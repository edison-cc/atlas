"""Tests for Jira issue fields and comment output. Runnable with pytest or directly."""

import io
import json
import sys
from argparse import ArgumentParser, Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from requests import ReadTimeout

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
    args = Namespace(keys=["DEMO-1"], fields="summary", comments=comments, json=json_output)
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


def _bulk_args(keys, *, comments=False):
    parser = ArgumentParser()
    jira_get.register(parser.add_subparsers())
    options = ["--comments"] if comments else []
    return parser.parse_args(["get", *keys, "--fields", "summary", "--json", *options])


def test_bulk_get_preserves_input_order_and_reports_partial_results():
    client = Mock()
    client.jira_post.return_value = {
        "issues": [
            {"key": "DEMO-1", "id": "101", "fields": {"summary": "One"}},
            {"key": "DEMO-2", "id": "102", "fields": {"summary": "Two", "comment": {"total": 1}}},
        ],
        "issueErrors": [{"id": "103", "errorMessage": "Issue exceeds the response size limit."}],
    }
    args = _bulk_args(["demo-2", "101", "DEMO-2", "103", "DEMO-999"], comments=True)
    with (
        patch.object(jira_get, "get_story_points_field", return_value=None),
        patch.object(jira_get, "get_acceptance_criteria_field", return_value="customfield_123"),
        redirect_stdout(io.StringIO()) as stdout,
        redirect_stderr(io.StringIO()) as stderr,
        TestCase().assertRaises(SystemExit) as failure,
    ):
        jira_get.run(args, client)

    assert failure.exception.code == 1
    client.jira_get.assert_not_called()
    client.jira_post.assert_called_once_with("issue/bulkfetch", json_body={
        "issueIdsOrKeys": ["demo-2", "101", "103", "DEMO-999"],
        "fields": ["summary", "comment", "customfield_123"],
    })
    result = json.loads(stdout.getvalue())
    assert result["schema_version"] == 1
    assert [item["key"] for item in result["items"]] == ["DEMO-2", "DEMO-1", "DEMO-2"]
    assert result["items"][0]["comments_pagination"] == {"returned": 0, "total": 1, "has_more": True}
    assert result["errors"] == [
        {"input": "103", "message": "Issue exceeds the response size limit."},
        {"input": "DEMO-999", "message": "Jira did not return an issue for this key or ID."},
    ]
    assert "103:" in stderr.getvalue() and "DEMO-999:" in stderr.getvalue()


def test_bulk_get_chunks_large_lists_and_keeps_their_order():
    for count, expected_sizes in [(50, [50]), (100, [100]), (101, [100, 1])]:
        keys = [f"DEMO-{index}" for index in range(count, 0, -1)]
        sizes = []

        def fetch(path, json_body):
            assert path == "issue/bulkfetch"
            identifiers = json_body["issueIdsOrKeys"]
            sizes.append(len(identifiers))
            return {"issues": [
                {"key": key, "id": key.split("-")[1], "fields": {}}
                for key in reversed(identifiers)
            ]}

        client = Mock()
        client.jira_post.side_effect = fetch
        items, errors = jira_get._fetch_bulk(client, keys, ["summary"], False)
        assert sizes == expected_sizes
        assert [item["key"] for item in items] == keys
        assert errors == []


def test_bulk_get_leaves_stdout_empty_when_a_later_request_fails():
    client = Mock()
    client.jira_post.side_effect = [
        {"issues": [{"key": "DEMO-1", "id": "101", "fields": {}}]},
        ReadTimeout(),
    ]
    args = _bulk_args([f"DEMO-{index}" for index in range(1, 102)])
    with (
        patch.object(jira_get, "get_story_points_field", return_value=None),
        patch.object(jira_get, "get_acceptance_criteria_field", return_value=None),
        redirect_stdout(io.StringIO()) as stdout,
        TestCase().assertRaises(ReadTimeout),
    ):
        jira_get.run(args, client)
    assert client.jira_post.call_count == 2
    assert stdout.getvalue() == ""


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
