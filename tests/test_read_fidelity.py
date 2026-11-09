"""Regression tests for Confluence Markdown and read pagination."""

import io
import json
import sys
import unittest
from argparse import ArgumentParser, Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from requests import HTTPError, Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import cli
from atlas.commands import conf_get, conf_search, conf_tree, jira_children, jira_get, jira_parent, jira_search
from atlas.confluence_storage import storage_to_markdown


def _search_args(*options):
    parser = ArgumentParser()
    jira_search.register(parser.add_subparsers(required=True))
    return parser.parse_args(["search", "project = DEV ORDER BY key ASC", *options])


class ReadFidelityTests(unittest.TestCase):
    def test_confluence_get_preserves_tables_code_and_links(self):
        client = Mock()
        client.confluence_get.return_value = {
            "title": "Design",
            "body": {"storage": {"value": (
                "<table><thead><tr><th>Name</th><th>Value</th></tr></thead>"
                "<tbody><tr><td>Timeout</td><td><code>A | B</code></td></tr></tbody></table>"
                '<p><a href="/wiki/link?a=1&amp;b=2">A &amp; B</a></p>'
                '<ac:structured-macro ac:name="code">'
                '<ac:parameter ac:name="language">python</ac:parameter>'
                '<ac:plain-text-body><![CDATA[x = "<tag>"\n\n\nprint(x)]]></ac:plain-text-body>'
                "</ac:structured-macro>"
            )}},
        }
        with redirect_stdout(io.StringIO()) as output:
            conf_get.run(Namespace(page_id="123", fmt="md", comments=False, json=False), client)
        text = output.getvalue()
        self.assertIn("| Name | Value |\n| --- | --- |\n| Timeout | `A \\| B` |", text)
        self.assertIn("[A & B](/wiki/link?a=1&b=2)", text)
        self.assertIn('```python\nx = "<tag>"\n\n\nprint(x)\n```', text)

    def test_confluence_merged_cells_keep_their_html_structure(self):
        table = '<table><tr><th colspan="2">Heading</th></tr><tr><td>A</td><td>B</td></tr></table>'
        self.assertEqual(storage_to_markdown(table), table)

    def test_confluence_cross_page_anchor_retains_page_reference(self):
        storage = (
            '<ac:link ac:anchor="details"><ri:page ri:content-title="Design" ri:space-key="DEV" />'
            "<ac:plain-text-link-body>Read more</ac:plain-text-link-body></ac:link>"
        )
        result = storage_to_markdown(storage)
        self.assertIn('ri:content-title="Design" ri:space-key="DEV"', result)
        self.assertIn('ac:anchor="details"', result)

    def test_confluence_comments_follow_next_link_on_a_short_page(self):
        client = Mock()
        client.confluence_get.side_effect = [
            {"results": [{"id": "1"}], "_links": {"next": "?start=1"}},
            {"results": [{"id": "2"}]},
        ]
        self.assertEqual(conf_get._fetch_all_page_comments(client, "123"), [{"id": "1"}, {"id": "2"}])
        self.assertEqual(client.confluence_get.call_args.kwargs["params"]["depth"], "all")

    def test_confluence_tree_finds_parent_on_the_next_page(self):
        client = Mock()
        client.confluence_get.side_effect = [
            {
                "results": [{"id": "2", "title": "Child", "ancestors": [{"id": "1"}]}],
                "_links": {"next": "/rest/api/content?start=1&next=opaque%2Btoken"},
            },
            {"results": [
                {"id": "1", "title": "Parent"},
                {"id": "3", "title": "Orphan", "ancestors": [{"id": "4"}]},
            ]},
        ]
        with redirect_stdout(io.StringIO()) as output:
            conf_tree.run(Namespace(space_key="DEV", depth=3, json=False), client)
        self.assertIn("Parent (1)\n  - Child (2)", output.getvalue())
        self.assertIn("### Pages with unavailable parents\nOrphan (3)", output.getvalue())
        path, = client.confluence_get.call_args.args
        self.assertEqual(path, "content")
        self.assertEqual(client.confluence_get.call_args.kwargs["params"], {
            "type": "page", "spaceKey": "DEV", "expand": "ancestors", "limit": 200,
            "start": "1", "next": "opaque+token",
        })

    def test_jira_children_searches_descendants_of_later_results(self):
        client = Mock()
        pages = [
            {"issues": [{"key": "DEV-2", "id": "2", "fields": {"parent": {"key": "DEV-1"}}}],
             "nextPageToken": "cursor", "isLast": False},
            {"issues": [{"key": "DEV-3", "id": "3"}], "isLast": True},
            {"issues": [{"key": "DEV-4", "id": "4", "fields": {"parent": {"key": "DEV-3"}}}], "isLast": True},
        ]
        client.jira_post.side_effect = pages
        with redirect_stdout(io.StringIO()) as output:
            jira_children.run(Namespace(key="DEV-1", depth=2, limit=1, story_points=False, json=False), client)
        self.assertIn("3 issues", output.getvalue())
        self.assertIn("| DEV-4 |", output.getvalue())
        queries = [call.kwargs["json_body"] for call in client.jira_post.call_args_list]
        self.assertEqual(queries[1]["nextPageToken"], "cursor")
        self.assertEqual(queries[2]["jql"], "parent in (DEV-2, DEV-3) ORDER BY key ASC")
        self.assertNotIn("nextPageToken", queries[2])
        self.assertTrue(all(query["maxResults"] == 1 for query in queries))

        client.reset_mock()
        client.jira_post.side_effect = pages
        with redirect_stdout(io.StringIO()) as json_output:
            jira_children.run(Namespace(key="DEV-1", depth=2, limit=1, story_points=False, json=True), client)
        payload = json.loads(json_output.getvalue())
        self.assertEqual(payload, {
            "schema_version": 1, "root_key": "DEV-1", "items": [
                {"key": "DEV-2", "id": "2", "parent_key": "DEV-1", "depth": 1,
                 "fields": {"parent": {"key": "DEV-1"}}},
                {"key": "DEV-3", "id": "3", "parent_key": None, "depth": 1, "fields": {}},
                {"key": "DEV-4", "id": "4", "parent_key": "DEV-3", "depth": 2,
                 "fields": {"parent": {"key": "DEV-3"}}},
            ],
        })
        self.assertTrue(all(f"| {item['key']} |" in output.getvalue() for item in payload["items"]))
        self.assertEqual([call.kwargs["json_body"] for call in client.jira_post.call_args_list], queries)

    def test_jira_parent_json_uses_the_same_chain_and_depth_limit(self):
        client = Mock()
        first = {"summary": "Child", "parent": {"key": "DEV-2"}}
        second = {"summary": "Parent", "parent": {"key": "DEV-3"}}
        pages = [{"id": "1", "fields": first}, {"id": "2", "fields": second}]
        client.jira_get.side_effect = pages
        with redirect_stdout(io.StringIO()) as output:
            jira_parent.run(Namespace(key="DEV-1", depth=1, json=True), client)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload, {
            "schema_version": 1, "root_key": "DEV-1", "items": [
                {"key": "DEV-1", "id": "1", "parent_key": "DEV-2", "depth": 0, "fields": first},
                {"key": "DEV-2", "id": "2", "parent_key": "DEV-3", "depth": 1, "fields": second},
            ],
        })
        self.assertEqual([call.args[0] for call in client.jira_get.call_args_list], ["issue/DEV-1", "issue/DEV-2"])
        client.jira_get.side_effect = pages
        with redirect_stdout(io.StringIO()) as markdown:
            jira_parent.run(Namespace(key="DEV-1", depth=1, json=False), client)
        self.assertIn("- DEV-1: Child", markdown.getvalue())
        self.assertIn("  - DEV-2: Parent", markdown.getvalue())

    def test_jira_children_fails_on_a_repeated_cursor(self):
        client = Mock()
        client.jira_post.return_value = {"issues": [], "nextPageToken": "same", "isLast": False}
        with self.assertRaisesRegex(SystemExit, "Results are incomplete"):
            jira_children._collect_children(client, ["DEV-1"], 1, 1, None)
        self.assertEqual(client.jira_post.call_count, 2)

    def test_search_marks_continuation_when_total_is_unknown(self):
        jira = Mock()
        jira.jira_get.return_value = {"issues": [{"key": "DEV-1"}], "nextPageToken": "cursor"}
        conf = Mock()
        conf.confluence_get.return_value = {
            "results": [{"content": {"id": "1"}}], "_links": {"next": "?cursor=abc"},
        }
        with redirect_stdout(io.StringIO()) as output:
            jira_search.run(_search_args("--fields", "summary"), jira)
            conf_search.run(Namespace(query="type = page", space=None, limit=1, json=False), conf)
        self.assertIn("## Jira: 1 results shown (more available)", output.getvalue())
        self.assertIn("## Confluence: 1 results shown (more available)", output.getvalue())
        jira.jira_get.assert_called_once_with("search/jql", params={
            "jql": "project = DEV ORDER BY key ASC", "fields": "summary", "maxResults": 20,
        })
        jira.jira_post.assert_not_called()
        conf.confluence_get.assert_called_once()

    def test_jira_json_keeps_requested_custom_fields_and_partial_metadata(self):
        client = Mock()
        fields = {"customfield_123": ["one", "two"]}
        client.jira_get.side_effect = [
            {"key": "DEV-1", "id": "1", "fields": fields},
            {"issues": [{"key": "DEV-1", "id": "1", "fields": fields}], "nextPageToken": "more"},
        ]
        with redirect_stdout(io.StringIO()) as output:
            jira_get.run(Namespace(key="DEV-1", fields="customfield_123", comments=False, json=True), client)
            jira_search.run(_search_args("--fields", "customfield_123", "--limit", "1", "--json"), client)
        issue, search = map(json.loads, output.getvalue().splitlines())
        self.assertEqual(issue, {"schema_version": 1, "key": "DEV-1", "id": "1", "fields": fields})
        self.assertEqual(search["items"], [{"key": "DEV-1", "id": "1", "fields": fields}])
        self.assertEqual(search["pagination"], {"returned": 1, "total": None, "has_more": True})
        self.assertEqual(client.jira_get.call_args.kwargs["params"]["fields"], "customfield_123")
        self.assertEqual(client.jira_get.call_args.kwargs["params"]["maxResults"], 1)

    def test_jira_search_paginate_follows_short_and_empty_pages(self):
        client = Mock()
        client.jira_post.side_effect = [
            {"issues": [{"key": "DEV-1"}], "nextPageToken": "first"},
            {"issues": [], "nextPageToken": "second"},
            {"issues": [{"key": "DEV-2"}, {"key": "DEV-3"}], "isLast": True},
        ]
        with redirect_stdout(io.StringIO()) as output:
            jira_search.run(_search_args("--fields", "key, summary", "--paginate", "--json"), client)
        result = json.loads(output.getvalue())
        self.assertEqual([issue["key"] for issue in result["items"]], ["DEV-1", "DEV-2", "DEV-3"])
        self.assertEqual(result["pagination"], {"returned": 3, "total": None, "has_more": False})
        queries = [call.kwargs["json_body"] for call in client.jira_post.call_args_list]
        base = {"jql": "project = DEV ORDER BY key ASC", "fields": ["key", "summary"], "maxResults": 100}
        self.assertEqual(queries, [base, {**base, "nextPageToken": "first"}, {**base, "nextPageToken": "second"}])
        client.jira_get.assert_not_called()

    def test_jira_search_paginated_limit_preserves_truncation_status(self):
        scenarios = [
            (["DEV-3"], {"isLast": True}, False),
            (["DEV-3", "DEV-4"], {"isLast": True}, True),
            (["DEV-3"], {"nextPageToken": "still-more"}, True),
        ]
        for keys, continuation, has_more in scenarios:
            with self.subTest(keys=keys, continuation=continuation):
                client = Mock()
                client.jira_post.side_effect = [
                    {"issues": [{"key": "DEV-1"}, {"key": "DEV-2"}], "nextPageToken": "next"},
                    {"issues": [{"key": key} for key in keys], **continuation},
                ]
                with redirect_stdout(io.StringIO()) as output:
                    jira_search.run(_search_args("--paginate", "--limit", "3", "--json"), client)
                result = json.loads(output.getvalue())
                self.assertEqual([issue["key"] for issue in result["items"]], ["DEV-1", "DEV-2", "DEV-3"])
                self.assertEqual(result["pagination"], {"returned": 3, "total": None, "has_more": has_more})
                self.assertEqual(client.jira_post.call_count, 2)

    def test_jira_search_rejects_incomplete_pagination_without_stdout(self):
        scenarios = [
            [{"issues": [{"key": "DEV-1"}], "isLast": False}],
            [{"issues": [{"key": "DEV-1"}], "isLast": True, "total": 3}],
            [{"issues": [{"key": "DEV-1"}], "nextPageToken": "repeat"}] * 2,
        ]
        for pages in scenarios:
            with self.subTest(pages=pages):
                client = Mock()
                client.jira_post.side_effect = pages
                with redirect_stdout(io.StringIO()) as output:
                    with self.assertRaisesRegex(SystemExit, "Results are incomplete"):
                        jira_search.run(_search_args("--paginate", "--json"), client)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(client.jira_post.call_count, len(pages))

    def test_jira_search_second_page_error_exits_without_partial_stdout(self):
        client = Mock()
        response = Response()
        response.status_code = 503
        client.jira_post.side_effect = [
            {"issues": [{"key": "DEV-1"}], "nextPageToken": "next"},
            HTTPError("API error (503)", response=response),
        ]
        argv = ["atlas", "jira", "search", "project = DEV", "--paginate", "--json"]
        with (
            patch.object(sys, "argv", argv),
            patch.object(cli, "load_config", return_value={}),
            patch("atlas.client.AtlassianClient", return_value=client),
            redirect_stdout(io.StringIO()) as output,
            self.assertRaisesRegex(SystemExit, r"API error \(503\)"),
        ):
            cli.main()
        self.assertEqual(output.getvalue(), "")

    def test_confluence_json_keeps_storage_and_applies_tree_depth(self):
        client = Mock()
        storage = '<p>Design &amp; planning</p>'
        client.confluence_get.side_effect = [
            {"id": "123", "title": "Design", "body": {"storage": {"value": storage}}},
            {"results": []},
            {"results": [
                {"id": "123", "title": "Design"},
                {"id": "124", "title": "Details", "ancestors": [{"id": "123"}]},
            ]},
        ]
        with redirect_stdout(io.StringIO()) as output:
            conf_get.run(Namespace(page_id="123", fmt="storage", comments=False, json=True), client)
            conf_search.run(Namespace(query="type = page", space=None, limit=1, json=True), client)
            conf_tree.run(Namespace(space_key="DEV", depth=1, json=True), client)
        page, search, tree = map(json.loads, output.getvalue().splitlines())
        self.assertEqual(page["body"], {"format": "storage", "value": storage})
        self.assertEqual(search["items"], [])
        self.assertEqual(search["pagination"], {"returned": 0, "total": None, "has_more": False})
        self.assertEqual(tree["fetched_count"], 2)
        self.assertEqual(tree["roots"], [{"id": "123", "title": "Design", "children": []}])


if __name__ == "__main__":
    unittest.main()
