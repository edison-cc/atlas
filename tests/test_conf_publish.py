"""Tests for the markdown -> Confluence storage converter in ``atlas conf publish``.

Covers the five converter bugs documented for well-formed GitHub-flavored
Markdown. Runnable with pytest or directly: ``python tests/test_conf_publish.py``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
