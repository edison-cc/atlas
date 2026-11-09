"""Regression tests for Confluence Markdown and read pagination."""

import io
import sys
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.commands import conf_get, conf_search, conf_tree, jira_children, jira_search
from atlas.confluence_storage import storage_to_markdown


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
            conf_get.run(Namespace(page_id="123", fmt="md", comments=False), client)
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
            conf_tree.run(Namespace(space_key="DEV", depth=3), client)
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
        client.jira_post.side_effect = [
            {"issues": [{"key": "DEV-2"}], "nextPageToken": "cursor", "isLast": False},
            {"issues": [{"key": "DEV-3"}], "isLast": True},
            {"issues": [{"key": "DEV-4", "fields": {"parent": {"key": "DEV-3"}}}], "isLast": True},
        ]
        with redirect_stdout(io.StringIO()) as output:
            jira_children.run(Namespace(key="DEV-1", depth=2, limit=1, story_points=False), client)
        self.assertIn("3 issues", output.getvalue())
        self.assertIn("| DEV-4 |", output.getvalue())
        queries = [call.kwargs["json_body"] for call in client.jira_post.call_args_list]
        self.assertEqual(queries[1]["nextPageToken"], "cursor")
        self.assertEqual(queries[2]["jql"], "parent in (DEV-2, DEV-3) ORDER BY key ASC")
        self.assertNotIn("nextPageToken", queries[2])
        self.assertTrue(all(query["maxResults"] == 1 for query in queries))

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
            jira_search.run(Namespace(
                jql="project = DEV", fields="summary", story_points=False, parent=False, limit=1,
            ), jira)
            conf_search.run(Namespace(query="type = page", space=None, limit=1), conf)
        self.assertIn("## Jira: 1 results shown (more available)", output.getvalue())
        self.assertIn("## Confluence: 1 results shown (more available)", output.getvalue())
        jira.jira_get.assert_called_once()
        conf.confluence_get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
