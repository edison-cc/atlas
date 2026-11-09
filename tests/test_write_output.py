"""Tests for JSON write results through the Atlas CLI."""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from requests import Response
from requests.adapters import HTTPAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import cli


_CONFIG = {
    "atlassian_base_url": "https://example.invalid",
    "atlassian_email": "example@example.invalid",
    "atlassian_api_token": "fake-token",
}


def _response(status, payload=None):
    response = Response()
    response.status_code = status
    response._content = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return response


class WriteOutputTests(unittest.TestCase):
    def setUp(self):
        config = patch.object(cli, "load_config", return_value=_CONFIG)
        config.start()
        self.addCleanup(config.stop)

    def run_json(self, args, responses, expected_requests):
        with (
            patch.object(sys, "argv", ["atlas", *args, "--json"]),
            patch.object(HTTPAdapter, "send", side_effect=responses) as send,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            cli.main()
        requests = [call.args[0] for call in send.call_args_list]
        self.assertEqual([(request.method, request.path_url) for request in requests], expected_requests)
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        return json.loads(stdout.getvalue())

    def test_create_and_comment_use_ids_from_the_write_response(self):
        cases = [
            (
                ["jira", "create", "--project", "DEMO", "--type", "Task", "--summary", "Work"],
                "/rest/api/3/issue",
                {"id": "100", "key": "DEMO-1"},
                {"operation": "jira.create", "key": "DEMO-1", "id": "100"},
            ),
            (
                ["jira", "comment", "DEMO-1", "Note"],
                "/rest/api/3/issue/DEMO-1/comment",
                {"id": "110"},
                {"operation": "jira.comment", "key": "DEMO-1", "comment_id": "110"},
            ),
            (
                ["conf", "create", "--space", "DEV", "--title", "設計"],
                "/wiki/rest/api/content",
                {"id": "120"},
                {"operation": "conf.create", "id": "120", "title": "設計"},
            ),
        ]
        for args, path, payload, result in cases:
            with self.subTest(command=args[:2]):
                actual = self.run_json(args, [_response(201, payload)], [("POST", path)])
                self.assertEqual(actual, {"schema_version": 1, **result})

    def test_jira_update_and_transition_handle_empty_204_responses(self):
        cases = [
            (
                ["jira", "update", "DEMO-1", "--summary", "Revised"],
                ("PUT", "/rest/api/3/issue/DEMO-1"),
                {"operation": "jira.update", "key": "DEMO-1", "changed": True},
            ),
            (
                ["jira", "transition", "DEMO-1", "31"],
                ("POST", "/rest/api/3/issue/DEMO-1/transitions"),
                {"operation": "jira.transition", "key": "DEMO-1", "transition_id": "31"},
            ),
        ]
        for args, request, result in cases:
            with self.subTest(command=args[:2]):
                actual = self.run_json(args, [_response(204)], [request])
                self.assertEqual(actual, {"schema_version": 1, **result})

    def test_jira_update_with_no_fields_returns_changed_false_without_a_request(self):
        self.assertEqual(self.run_json(["jira", "update", "DEMO-1"], [], []), {
            "schema_version": 1,
            "operation": "jira.update",
            "key": "DEMO-1",
            "changed": False,
        })

    def test_confluence_update_reports_the_submitted_version(self):
        path = "/wiki/rest/api/content/120"
        responses = [
            _response(200, {
                "title": "Design",
                "version": {"number": 7},
                "body": {"storage": {"value": "<p>Existing body</p>"}},
            }),
            _response(200, {}),
        ]
        actual = self.run_json(
            ["conf", "update", "120", "--title", "Revised"],
            responses,
            [("GET", path + "?expand=version%2Cbody.storage"), ("PUT", path)],
        )
        self.assertEqual(actual, {
            "schema_version": 1,
            "operation": "conf.update",
            "id": "120",
            "title": "Revised",
            "version": 8,
        })

    def test_failed_write_leaves_stdout_empty(self):
        with (
            patch.object(sys, "argv", ["atlas", "jira", "comment", "DEMO-1", "Note", "--json"]),
            patch.object(HTTPAdapter, "send", return_value=_response(403, {"message": "Forbidden"})) as send,
            redirect_stdout(io.StringIO()) as stdout,
            self.assertRaisesRegex(SystemExit, "403"),
        ):
            cli.main()
        send.assert_called_once()
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
