"""Tests for bounded retries and CLI diagnostics."""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from requests import HTTPError, ReadTimeout, Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import cli
from atlas.client import AtlassianClient, request_error_message


_CONFIG = {
    "atlassian_base_url": "https://example.invalid",
    "atlassian_email": "example@example.invalid",
    "atlassian_api_token": "fake-token",
}


def response(status, retry_after=None):
    result = Response()
    result.status_code = status
    result._content = json.dumps({"issues": []}).encode()
    if retry_after is not None:
        result.headers["Retry-After"] = retry_after
    return result


class RequestErrorTests(unittest.TestCase):
    def test_read_only_jira_posts_retry_once_after_throttling(self):
        client = AtlassianClient(_CONFIG)
        for path, payload in [
            ("search/jql", {"jql": "project = DEMO"}),
            ("issue/bulkfetch", {"issueIdsOrKeys": ["DEMO-1", "DEMO-2"]}),
        ]:
            with (
                self.subTest(path=path),
                patch.object(client.session, "request", side_effect=[response(429, "2"), response(200)]) as send,
                patch("atlas.client.sleep") as sleep,
            ):
                self.assertEqual(client.jira_post(path, payload), {"issues": []})
                sleep.assert_called_once_with(2)
                self.assertEqual(send.call_args_list[0], send.call_args_list[1])

    def test_repeated_throttling_ends_after_one_retry(self):
        client = AtlassianClient(_CONFIG)
        with (
            patch.object(client.session, "request", return_value=response(429, "1")) as send,
            patch("atlas.client.sleep") as sleep,
            self.assertRaises(HTTPError),
        ):
            client.jira_get("issue/DEMO-1")
        sleep.assert_called_once_with(1)
        self.assertEqual(send.call_count, 2)

    def test_rate_limited_write_and_long_delay_read_fail_without_retry(self):
        client = AtlassianClient(_CONFIG)
        cases = [
            (lambda: client.confluence_put("content/1", {"title": "New"}), "1"),
            (lambda: client.confluence_get("content/1"), "120"),
        ]
        for request, delay in cases:
            with self.subTest(delay=delay):
                with (
                    patch.object(client.session, "request", return_value=response(429, delay)) as send,
                    patch("atlas.client.sleep") as sleep,
                    self.assertRaises(HTTPError) as raised,
                ):
                    request()
                send.assert_called_once()
                sleep.assert_not_called()
                self.assertIn(f"Wait at least {delay} seconds", request_error_message(raised.exception))

    def test_cli_handles_timeout_without_partial_stdout(self):
        with (
            patch.object(sys, "argv", ["atlas", "jira", "get", "DEMO-1"]),
            patch.object(cli, "load_config", return_value=_CONFIG),
            patch.object(AtlassianClient, "jira_get", side_effect=ReadTimeout()),
            redirect_stdout(io.StringIO()) as stdout,
            self.assertRaisesRegex(SystemExit, "Atlassian request timed out"),
        ):
            cli.main()
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
