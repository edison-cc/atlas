"""Tests for Confluence publishing and the Markdown to storage converter.

Runnable with pytest or directly: ``python tests/test_conf_publish.py``.
"""

import base64
import hashlib
import io
import json
import sys
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from email import policy
from email.parser import BytesParser
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from requests import HTTPError, Response
from requests.adapters import HTTPAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import cli  # noqa: E402
from atlas.client import AtlassianClient  # noqa: E402
from atlas.commands import conf_publish  # noqa: E402
from atlas.commands.conf_publish import _markdown_to_storage as convert  # noqa: E402


def test_bug1_softwrap_joins_paragraph():
    # A single newline is a soft break (space), not a paragraph boundary, so an
    # inline span opened on one wrapped line and closed on the next stays intact.
    assert convert("foo **bar\nbaz** qux") == "<p>foo <strong>bar baz</strong> qux</p>"


def test_bug1_softwrap_italic_across_lines():
    assert convert("knows *which\norg* here") == "<p>knows <em>which org</em> here</p>"


def test_bug1_blank_line_still_splits_paragraphs():
    assert convert("one.\n\ntwo.") == "<p>one.</p><p>two.</p>"


def test_bug1_list_item_softwrap_joins():
    assert convert("- alpha\n  beta") == "<ul><li>alpha beta</li></ul>"


def test_bug2_escaped_pipe_in_table_cell():
    md = "| col |\n|-----|\n| a \\| b |"
    assert convert(md) == (
        "<table><tbody><tr><th>col</th></tr>"
        "<tr><td>a | b</td></tr></tbody></table>"
    )


def test_bug2_multiple_unions_do_not_explode_columns():
    md = "| p | v |\n|---|---|\n| x | `str \\| None`, `int \\| None` |"
    assert convert(md) == (
        "<table><tbody><tr><th>p</th><th>v</th></tr>"
        "<tr><td>x</td><td><code>str | None</code>, <code>int | None</code></td></tr>"
        "</tbody></table>"
    )


def test_bug3_inline_code_in_heading():
    assert convert("# Title `code`") == "<h1>Title <code>code</code></h1>"


def test_bug4_angle_brackets_in_inline_code():
    assert convert("use `Bearer <token>` here") == (
        "<p>use <code>Bearer &lt;token&gt;</code> here</p>"
    )


def test_bug4_angle_brackets_in_text():
    assert convert("token is <signed token> ok") == (
        "<p>token is &lt;signed token&gt; ok</p>"
    )


def test_bug5_bold_around_code_span():
    assert convert("**`x` = y**") == "<p><strong><code>x</code> = y</strong></p>"


def test_bug5_bold_wrapping_only_code_span():
    assert convert("- **`brightdrop-web`** - the web") == (
        "<ul><li><strong><code>brightdrop-web</code></strong> - the web</li></ul>"
    )


def test_regression_normal_table():
    md = "| a | b |\n|---|---|\n| 1 | 2 |"
    assert convert(md) == (
        "<table><tbody><tr><th>a</th><th>b</th></tr>"
        "<tr><td>1</td><td>2</td></tr></tbody></table>"
    )


def test_regression_fenced_code_block_escapes_and_uses_cdata():
    md = "```python\nx = 1 < 2 and a & b\n```"
    assert convert(md) == (
        '<ac:structured-macro ac:name="code">'
        '<ac:parameter ac:name="language">python</ac:parameter>'
        "<ac:plain-text-body><![CDATA[x = 1 &lt; 2 and a &amp; b]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )


def test_regression_http_link():
    assert convert("see [docs](https://ex.com/a)") == (
        '<p>see <a href="https://ex.com/a">docs</a></p>'
    )


def test_regression_anchor_link():
    assert convert("see [section](#sec)") == (
        '<p>see <ac:link ac:anchor="sec">'
        "<ac:link-body>section</ac:link-body></ac:link></p>"
    )


def test_regression_http_and_anchor_link_on_same_line():
    # The two links must be matched independently; the anchor-link text group
    # must not swallow the preceding http link.
    assert convert("see [docs](https://ex.com/a) and [anchor](#sec)") == (
        '<p>see <a href="https://ex.com/a">docs</a> and '
        '<ac:link ac:anchor="sec"><ac:link-body>anchor</ac:link-body></ac:link></p>'
    )


_DIAGRAM = "```mermaid\ngraph TD\nA --> B\n```"
_PNG_DATA = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9ioAAAAASUVORK5CYII="
)
_ATTACHMENT = f"atlas-diagram-{hashlib.sha256(_PNG_DATA).hexdigest()}.png"
_CONFIG = {
    "atlassian_base_url": "https://example.invalid",
    "atlassian_email": "example@example.invalid",
    "atlassian_api_token": "fake-token",
}


def _publish_input(directory, content):
    path = Path(directory) / "design.md"
    path.write_text(content, encoding="utf-8")
    return Namespace(input_file=path, page_id="123", title="Design", minor=False, dry_run=False, diff=False, json=False)


def test_second_render_failure_aborts_before_any_api_call():
    client = Mock(spec=AtlassianClient)
    error = conf_publish.PublishError("second diagram failed")
    with TemporaryDirectory() as directory, patch.object(conf_publish.shutil, "which", return_value="mmdc"), \
            patch.object(conf_publish, "_render_mermaid", side_effect=[_PNG_DATA, error]) as render, \
            redirect_stderr(io.StringIO()) as stderr, TestCase().assertRaises(SystemExit) as failure:
        args = _publish_input(directory, f"# Design\n\n{_DIAGRAM}\n\n{_DIAGRAM}")
        conf_publish.run(args, client)
    assert failure.exception.code == 1
    assert render.call_count == 2
    assert "second diagram failed" in stderr.getvalue()
    assert client.mock_calls == []


def test_missing_renderer_aborts_before_any_api_call():
    client = Mock(spec=AtlassianClient)
    with TemporaryDirectory() as directory, patch.object(conf_publish.shutil, "which", return_value=None), \
            redirect_stderr(io.StringIO()) as stderr, TestCase().assertRaises(SystemExit) as failure:
        conf_publish.run(_publish_input(directory, _DIAGRAM), client)
    assert failure.exception.code == 1
    assert "Mermaid diagrams require mmdc" in stderr.getvalue()
    assert client.mock_calls == []


def test_mermaid_scanner_ignores_examples_and_rejects_unclosed_fences():
    example = f"````md\n{_DIAGRAM}\n````"
    assert conf_publish._prepare_diagrams(example) == (example, {})
    with TestCase().assertRaises(conf_publish.PublishError) as failure:
        conf_publish._prepare_diagrams("~~~mermaid\ngraph TD\nA --> B")
    assert "Unclosed Mermaid" in str(failure.exception)


def test_dry_run_uses_real_cli_path_without_credentials():
    with TemporaryDirectory() as directory:
        args = _publish_input(directory, f"# Design\n\n{_DIAGRAM}\n\n{_DIAGRAM}")
        argv = ["atlas", "conf", "publish", "123", str(args.input_file), "--title", "Design", "--dry-run"]
        with patch.object(cli, "load_config") as config, \
                patch("atlas.client.AtlassianClient") as client, \
                patch.object(conf_publish.shutil, "which", return_value="mmdc"), \
                patch.object(conf_publish, "_render_mermaid", return_value=_PNG_DATA), \
                redirect_stderr(io.StringIO()):
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()) as stdout:
                cli.main()
            with patch.object(sys, "argv", [*argv, "--json"]), redirect_stdout(io.StringIO()) as json_stdout:
                cli.main()
    config.assert_not_called()
    client.assert_not_called()
    preview = stdout.getvalue()
    assert "Dry run for page 123: Design" in preview
    assert preview.splitlines()[1] == f"Attachments: {_ATTACHMENT}"
    assert "<h1>Design</h1>" in preview
    assert preview.count(f'ri:filename="{_ATTACHMENT}"') == 2
    assert json.loads(json_stdout.getvalue()) == {
        "schema_version": 1,
        "operation": "conf.publish",
        "id": "123",
        "title": "Design",
        "dry_run": True,
        "attachments": [_ATTACHMENT],
        "body": {"format": "storage", "value": preview.split("\n\n", 1)[1].removesuffix("\n")},
    }


def test_publish_version_conflict_reports_uploaded_files_and_does_not_retry():
    client = Mock(spec=AtlassianClient)
    client.confluence_get.return_value = {"version": {"number": 4}}
    client.confluence_upload.return_value = True
    response = Response()
    response.status_code = 409
    client.confluence_put.side_effect = HTTPError(response=response)
    with TemporaryDirectory() as directory, patch.object(conf_publish.shutil, "which", return_value="mmdc"), \
            patch.object(conf_publish, "_render_mermaid", return_value=_PNG_DATA), \
            redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr, \
            TestCase().assertRaises(SystemExit) as failure:
        args = _publish_input(directory, f"{_DIAGRAM}\n\n{_DIAGRAM}")
        args.json = True
        conf_publish.run(args, client)
    assert failure.exception.code == 1
    assert stdout.getvalue() == ""
    assert "Page 123 has a version conflict (read version 4)" in stderr.getvalue()
    assert f"Attachments uploaded before failure: {_ATTACHMENT}" in stderr.getvalue()
    assert [entry[0] for entry in client.mock_calls] == ["confluence_get", "confluence_upload", "confluence_put"]
    client.confluence_upload.assert_called_once_with("123", _ATTACHMENT, _PNG_DATA, "image/png")
    payload = client.confluence_put.call_args.kwargs["json_body"]
    assert payload["version"]["number"] == 5
    assert payload["body"]["storage"]["value"].count(f'ri:filename="{_ATTACHMENT}"') == 2


def test_attachment_duplicate_is_reused_only_when_filename_matches():
    client = AtlassianClient(_CONFIG)
    duplicate = Mock(ok=False, status_code=400, text="duplicate")
    for filename in (_ATTACHMENT, "other.png"):
        lookup = Mock(ok=True, status_code=200)
        lookup.json.return_value = {"results": [{"title": filename}]}
        with patch.object(client.session, "request", side_effect=[duplicate, lookup]) as request:
            if filename == _ATTACHMENT:
                assert client.confluence_upload("123", _ATTACHMENT, _PNG_DATA, "image/png") is False
            else:
                with TestCase().assertRaises(HTTPError):
                    client.confluence_upload("123", _ATTACHMENT, _PNG_DATA, "image/png")
            assert [entry.args[0] for entry in request.call_args_list] == ["POST", "GET"]
            assert request.call_args.kwargs["params"] == {"filename": _ATTACHMENT}


def _http_response(status, payload):
    response = Response()
    response.status_code = status
    response._content = json.dumps(payload).encode("utf-8")
    return response


def test_cli_publish_diff_shows_title_body_and_proposed_attachments_with_one_get():
    current = {
        "title": "Old design",
        "version": {"number": 4},
        "body": {"storage": {"value": "<h1>Old design</h1>"}},
    }
    with (
        TemporaryDirectory() as directory,
        patch.object(cli, "load_config", return_value=_CONFIG),
        patch.object(conf_publish.shutil, "which", return_value="mmdc"),
        patch.object(conf_publish, "_render_mermaid", return_value=_PNG_DATA),
        patch.object(HTTPAdapter, "send", side_effect=[_http_response(200, current)]) as send,
        redirect_stdout(io.StringIO()) as stdout,
        redirect_stderr(io.StringIO()) as stderr,
    ):
        args = _publish_input(directory, f"# Design\n\n{_DIAGRAM}\n\n{_DIAGRAM}")
        argv = ["atlas", "conf", "publish", "123", str(args.input_file), "--title", "Design", "--diff"]
        with patch.object(sys, "argv", argv):
            cli.main()

    send.assert_called_once()
    request = send.call_args.args[0]
    assert request.method == "GET"
    assert request.path_url == "/wiki/rest/api/content/123?expand=body.storage%2Cversion"
    preview = stdout.getvalue()
    assert "Diff for page 123 (version 4)" in preview
    assert "Title: 'Old design' -> 'Design'" in preview
    assert f"Proposed attachments: {_ATTACHMENT}\n" in preview
    assert "--- current.storage\n+++ proposed.storage" in preview
    assert "-<h1>Old design</h1>" in preview
    assert "+<h1>Design</h1>" in preview
    assert preview.count(f'ri:filename="{_ATTACHMENT}"') == 2
    assert "Rendering diagram" in stderr.getvalue()


def test_cli_publish_diff_json_reports_an_unchanged_page():
    current = {
        "title": "Design",
        "version": {"number": 4},
        "body": {"storage": {"value": "<h1>Design</h1>"}},
    }
    with (
        TemporaryDirectory() as directory,
        patch.object(cli, "load_config", return_value=_CONFIG),
        patch.object(HTTPAdapter, "send", side_effect=[_http_response(200, current)]) as send,
        redirect_stdout(io.StringIO()) as stdout,
    ):
        args = _publish_input(directory, "# Design")
        argv = ["atlas", "conf", "publish", "123", str(args.input_file), "--title", "Design", "--diff", "--json"]
        with patch.object(sys, "argv", argv):
            cli.main()

    send.assert_called_once()
    assert send.call_args.args[0].method == "GET"
    assert json.loads(stdout.getvalue()) == {
        "schema_version": 1,
        "operation": "conf.publish.diff",
        "id": "123",
        "version": 4,
        "current_title": "Design",
        "title": "Design",
        "changed": False,
        "diff": "",
        "attachments": [],
    }


def test_publish_diff_fails_if_current_storage_is_unavailable():
    client = Mock(spec=AtlassianClient)
    client.confluence_get.return_value = {"title": "Design", "version": {"number": 4}}
    with (
        TemporaryDirectory() as directory,
        redirect_stdout(io.StringIO()) as stdout,
        redirect_stderr(io.StringIO()) as stderr,
        TestCase().assertRaises(SystemExit) as failure,
    ):
        args = _publish_input(directory, "# Design")
        args.diff = True
        args.json = True
        conf_publish.run(args, client)

    assert failure.exception.code == 1
    assert stdout.getvalue() == ""
    assert "storage body" in stderr.getvalue()
    assert [entry[0] for entry in client.mock_calls] == ["confluence_get"]


def test_cli_publish_rejects_combining_diff_with_offline_dry_run():
    argv = ["atlas", "conf", "publish", "123", "design.md", "--title", "Design", "--diff", "--dry-run"]
    with (
        patch.object(sys, "argv", argv),
        patch.object(cli, "load_config") as config,
        redirect_stdout(io.StringIO()) as stdout,
        redirect_stderr(io.StringIO()) as stderr,
        TestCase().assertRaises(SystemExit) as failure,
    ):
        cli.main()

    config.assert_not_called()
    assert failure.exception.code == 2
    assert stdout.getvalue() == ""
    assert "not allowed with argument" in stderr.getvalue()


def _renderer_writes(data):
    def render(command, **kwargs):
        if data is not None:
            Path(command[command.index("-o") + 1]).write_bytes(data)
        return CompletedProcess(command, 0, stdout="", stderr="")
    return render


def test_cli_publish_and_retry_keep_one_attachment_and_update_the_page():
    page_url = "/wiki/rest/api/content/123"
    attachments_url = page_url + "/child/attachment"
    page_link = "/spaces/DEV/pages/123/Design"
    responses = [
        _http_response(200, {"version": {"number": 4}, "_links": {"webui": page_link}}),
        _http_response(200, {"results": [{"title": _ATTACHMENT}]}),
        _http_response(200, {}),
        _http_response(200, {"version": {"number": 5}, "_links": {"webui": page_link}}),
        _http_response(409, {"message": "attachment already exists"}),
        _http_response(200, {"results": [{"title": _ATTACHMENT}]}),
        _http_response(200, {}),
    ]
    with (
        TemporaryDirectory() as directory,
        patch.object(cli, "load_config", return_value=_CONFIG),
        patch.object(conf_publish.shutil, "which", return_value="mmdc"),
        patch.object(conf_publish.subprocess, "run", side_effect=_renderer_writes(_PNG_DATA)),
        patch.object(HTTPAdapter, "send", side_effect=responses) as send,
        redirect_stdout(io.StringIO()) as stdout,
        redirect_stderr(io.StringIO()) as stderr,
    ):
        args = _publish_input(directory, f"# Design\n\n{_DIAGRAM}\n\n{_DIAGRAM}")
        argv = ["atlas", "conf", "publish", "123", str(args.input_file), "--title", "Design", "--minor"]
        with patch.object(sys, "argv", argv):
            cli.main()
        with patch.object(sys, "argv", [*argv, "--json"]):
            cli.main()

    requests = [call.args[0] for call in send.call_args_list]
    assert [(request.method, request.path_url) for request in requests] == [
        ("GET", page_url + "?expand=version"),
        ("POST", attachments_url),
        ("PUT", page_url),
        ("GET", page_url + "?expand=version"),
        ("POST", attachments_url),
        ("GET", attachments_url + f"?filename={_ATTACHMENT}"),
        ("PUT", page_url),
    ]
    upload = requests[1]
    assert upload.headers["X-Atlassian-Token"] == "nocheck"
    envelope = f"Content-Type: {upload.headers['Content-Type']}\r\n\r\n".encode() + upload.body
    file, = BytesParser(policy=policy.default).parsebytes(envelope).iter_parts()
    assert file.get_filename() == _ATTACHMENT
    assert file.get_content_type() == "image/png"
    assert file.get_payload(decode=True) == _PNG_DATA

    first, retry = (json.loads(requests[index].body) for index in (2, 6))
    assert first["version"] == {"number": 5, "minorEdit": True}
    assert retry["version"] == {"number": 6, "minorEdit": True}
    assert first["title"] == retry["title"] == "Design"
    assert first["body"] == retry["body"]
    assert retry["body"]["storage"]["value"].count(f'ri:filename="{_ATTACHMENT}"') == 2
    text_result, json_result = stdout.getvalue().splitlines()
    url = f"https://example.invalid/wiki{page_link}"
    assert text_result == f"Published: {url}"
    assert json.loads(json_result) == {
        "schema_version": 1,
        "operation": "conf.publish",
        "id": "123",
        "title": "Design",
        "version": 6,
        "url": url,
        "dry_run": False,
        "attachments": [_ATTACHMENT],
    }
    assert f"Reusing attachment {_ATTACHMENT}" in stderr.getvalue()


def test_failed_second_upload_reports_only_completed_attachment_and_skips_page_update():
    client = AtlassianClient(_CONFIG)
    responses = [
        _http_response(200, {"version": {"number": 4}}),
        _http_response(200, {}),
        _http_response(403, {"message": "attachment upload denied"}),
    ]
    with (
        TemporaryDirectory() as directory,
        patch.object(conf_publish.shutil, "which", return_value="mmdc"),
        patch.object(conf_publish, "_render_mermaid", side_effect=[_PNG_DATA, b"different rendered PNG"]),
        patch.object(HTTPAdapter, "send", side_effect=responses) as send,
        redirect_stdout(io.StringIO()) as stdout,
        redirect_stderr(io.StringIO()) as stderr,
        TestCase().assertRaises(SystemExit) as failure,
    ):
        args = _publish_input(directory, f"{_DIAGRAM}\n\n{_DIAGRAM}")
        args.json = True
        conf_publish.run(args, client)

    assert failure.exception.code == 1
    assert stdout.getvalue() == ""
    assert [call.args[0].method for call in send.call_args_list] == ["GET", "POST", "POST"]
    assert "attachment upload denied" in stderr.getvalue()
    assert stderr.getvalue().splitlines()[-1] == f"Attachments uploaded before failure: {_ATTACHMENT}"


def test_successful_renderer_exit_requires_complete_png_before_any_api_call():
    for output, diagnostic in (
        (None, "did not produce"),
        (_PNG_DATA[:-12], "incomplete or invalid PNG"),
    ):
        client = Mock(spec=AtlassianClient)
        with (
            TemporaryDirectory() as directory,
            patch.object(conf_publish.shutil, "which", return_value="mmdc"),
            patch.object(conf_publish.subprocess, "run", side_effect=_renderer_writes(output)),
            redirect_stderr(io.StringIO()) as stderr,
            TestCase().assertRaises(SystemExit) as failure,
        ):
            conf_publish.run(_publish_input(directory, _DIAGRAM), client)
        assert failure.exception.code == 1
        assert diagnostic in stderr.getvalue()
        assert client.mock_calls == []


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
