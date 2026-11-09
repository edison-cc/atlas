"""atlas conf publish <PAGE-ID> <input.md> -- full Confluence publish workflow.

Renders Mermaid diagrams to PNG, uploads as attachments, converts markdown to
Confluence storage format, and publishes. Absorbs the logic from the former
confluence-publish skill's publish_with_diagrams.py.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from requests import HTTPError, RequestException

from atlas.client import request_error_message


class PublishError(Exception):
    """A local validation or publication failure."""


def register(subparser):
    p = subparser.add_parser(
        "publish", help="Publish markdown file to Confluence page"
    )
    p.add_argument("page_id", help="Numeric page ID to update")
    p.add_argument("input_file", help="Path to markdown file")
    p.add_argument("--title", required=True, help="Page title")
    p.add_argument("--minor", action="store_true", help="Mark as minor edit")
    p.add_argument(
        "--dry-run", action="store_true",
        help="Render locally and preview the page body and attachments without connecting to Confluence",
    )
    p.set_defaults(func=run)


def run(args, client):
    uploaded = []
    try:
        content = Path(args.input_file).read_text(encoding="utf-8")
        content, attachments = _prepare_diagrams(content)
        storage_content = _markdown_to_storage(content)
        if args.dry_run:
            print(f"Dry run for page {args.page_id}: {args.title}")
            print(f"Attachments: {', '.join(attachments) or 'none'}")
            print(f"\n{storage_content}")
            return
        _publish(args, client, storage_content, attachments, uploaded)
    except (PublishError, RequestException, OSError, UnicodeError) as error:
        message = request_error_message(error) if isinstance(error, RequestException) else str(error)
        print(f"Publish failed: {message}", file=sys.stderr)
        if uploaded:
            print(f"Attachments uploaded before failure: {', '.join(uploaded)}", file=sys.stderr)
        sys.exit(1)


def _publish(args, client, storage_content, attachments, uploaded):
    path = f"content/{args.page_id}"
    current = client.confluence_get(path, params={"expand": "version"})
    version = current["version"]["number"]

    payload = {
        "version": {"number": version + 1, "minorEdit": args.minor},
        "title": args.title,
        "type": "page",
        "body": {
            "storage": {
                "value": storage_content,
                "representation": "storage",
            }
        },
    }

    for filename, data in attachments.items():
        print(f"Sending attachment {filename}...", file=sys.stderr)
        if client.confluence_upload(args.page_id, filename, data, "image/png"):
            uploaded.append(filename)
        else:
            print(f"Reusing attachment {filename}", file=sys.stderr)

    try:
        client.confluence_put(path, json_body=payload)
    except HTTPError as error:
        if error.response.status_code == 409:
            raise PublishError(
                f"Page {args.page_id} has a version conflict (read version {version}). "
                "Review the latest page before publishing again."
            ) from error
        raise

    base_url = client.base_url.rstrip("/")
    web_link = current.get("_links", {}).get("webui", "")
    print(f"Published: {base_url}/wiki{web_link}" if web_link else f"Published page {args.page_id}")


# ---------------------------------------------------------------------------
# Mermaid diagram rendering
# ---------------------------------------------------------------------------

_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_END = bytes.fromhex("00000000 49454e44 ae426082")


def _find_chrome() -> str | None:
    from_env = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
    if from_env and Path(from_env).exists():
        return from_env
    for p in _CHROME_PATHS:
        if Path(p).exists():
            return p
    return None


def _render_mermaid(renderer: str, source: str, output_path: Path) -> bytes:
    input_path = output_path.with_suffix(".mmd")
    input_path.write_text(source, encoding="utf-8")
    cmd = [renderer, "-i", str(input_path), "-o", str(output_path), "-b", "white", "-s", "2"]
    chrome = _find_chrome()
    if chrome:
        config_path = output_path.with_suffix(".puppeteer.json")
        config_path.write_text(json.dumps({"executablePath": chrome}), encoding="utf-8")
        cmd.extend(["-p", str(config_path)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=60)
    except subprocess.TimeoutExpired as error:
        raise PublishError(f"Mermaid renderer timed out for {output_path.name}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or f"mmdc exited with status {result.returncode}"
        raise PublishError(f"Mermaid renderer failed for {output_path.name}: {detail}")
    if not output_path.is_file():
        raise PublishError(f"Mermaid renderer did not produce {output_path.name}")
    data = output_path.read_bytes()
    if not data.startswith(_PNG_SIGNATURE) or not data.endswith(_PNG_END):
        raise PublishError(f"Mermaid renderer produced an incomplete or invalid PNG: {output_path.name}")
    return data


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$", re.MULTILINE)


def _mermaid_blocks(content: str):
    """Yield fenced Mermaid blocks, ignoring fences inside other code blocks."""
    opening = None
    for match in _FENCE.finditer(content):
        marker, info = match.groups()
        if opening is None:
            if marker[0] == "~" or "`" not in info:
                opening = match
        elif not info.strip() and marker.startswith(opening[1]):
            if opening[2].strip() == "mermaid":
                yield opening.start(), match.end(), content[opening.end():match.start()].strip()
            opening = None
    if opening is not None and opening[2].strip() == "mermaid":
        raise PublishError("Unclosed Mermaid code block")


def _prepare_diagrams(content: str) -> tuple[str, dict[str, bytes]]:
    blocks = list(_mermaid_blocks(content))
    if not blocks:
        return content, {}
    renderer = shutil.which("mmdc")
    if renderer is None:
        raise PublishError("Mermaid diagrams require mmdc (npm install -g @mermaid-js/mermaid-cli)")

    parts = []
    attachments = {}
    offset = 0
    with tempfile.TemporaryDirectory() as directory:
        for index, (start, end, source) in enumerate(blocks, 1):
            print(f"Rendering diagram {index}...", file=sys.stderr)
            data = _render_mermaid(renderer, source, Path(directory) / f"diagram-{index}.png")
            filename = f"atlas-diagram-{hashlib.sha256(data).hexdigest()}.png"
            attachments[filename] = data
            parts.extend([
                content[offset:start],
                '<ac:image ac:align="center" ac:custom-width="true" ac:layout="center" ac:width="550">'
                f'<ri:attachment ri:filename="{filename}" /></ac:image>',
            ])
            offset = end
    parts.append(content[offset:])
    return "".join(parts), attachments


# ---------------------------------------------------------------------------
# Markdown -> Confluence storage format
# ---------------------------------------------------------------------------

def _is_block_boundary(line: str) -> bool:
    """Whether a line starts a new block and therefore cannot be a soft-wrapped
    continuation of the current paragraph or list item (CommonMark: only a blank
    line, or the start of another block, ends a paragraph)."""
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("```"):
        return True
    if stripped.startswith("|") and stripped.endswith("|"):
        return True
    if re.match(r"^#{1,6} ", stripped):
        return True
    if re.match(r"^---+$", stripped):
        return True
    if re.match(r"^- ", stripped):
        return True
    if re.match(r"^\s+- ", line):
        return True
    if stripped.startswith("<"):
        return True
    return False


def _markdown_to_storage(md: str) -> str:
    lines = md.split("\n")
    result = []
    i = 0
    in_list = False
    table_buf: list[str] = []
    in_table = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```") and not stripped.startswith("<ac:"):
            if in_list:
                result.append("</ul>")
                in_list = False
            if in_table:
                result.append(_convert_table(table_buf))
                table_buf, in_table = [], False
            html, i = _convert_code_block(lines, i)
            result.append(html)
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            if in_list:
                result.append("</ul>")
                in_list = False
            in_table = True
            table_buf.append(stripped)
            i += 1
            continue
        elif in_table:
            result.append(_convert_table(table_buf))
            table_buf, in_table = [], False

        heading = re.match(r"^(#{1,6}) (.+)$", stripped)
        if heading:
            if in_list:
                result.append("</ul>")
                in_list = False
            level = len(heading.group(1))
            result.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if re.match(r"^---+$", stripped):
            if in_list:
                result.append("</ul>")
                in_list = False
            result.append("<hr />")
            i += 1
            continue

        checkbox = re.match(r"^- \[( |x|X)\] (.+)$", stripped)
        if checkbox:
            if in_list:
                result.append("</ul>")
                in_list = False
            html, i = _convert_checkboxes(lines, i)
            result.append(html)
            continue

        list_item = re.match(r"^- (.+)$", stripped)
        if list_item:
            if not in_list:
                result.append("<ul>")
                in_list = True
            item_text = list_item.group(1)
            i += 1
            while i < len(lines) and not _is_block_boundary(lines[i]):
                item_text += " " + lines[i].strip()
                i += 1
            result.append(f"<li>{_inline(item_text)}</li>")
            continue

        indented_item = re.match(r"^\s+- (.+)$", line)
        if indented_item:
            item_text = indented_item.group(1)
            i += 1
            while i < len(lines) and not _is_block_boundary(lines[i]):
                item_text += " " + lines[i].strip()
                i += 1
            result.append(f"<li>{_inline(item_text)}</li>")
            continue

        if in_list and stripped and not stripped.startswith("-"):
            result.append("</ul>")
            in_list = False

        if "<ac:image" in stripped or "<ac:" in stripped:
            result.append(stripped)
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        if not stripped.startswith("<"):
            # Join soft-wrapped lines into one paragraph; a single newline is a
            # soft break (space), only a blank line or new block ends the
            # paragraph (Bug 1 / CommonMark §4.8).
            para = [stripped]
            i += 1
            while i < len(lines) and not _is_block_boundary(lines[i]):
                para.append(lines[i].strip())
                i += 1
            result.append(f"<p>{_inline(' '.join(para))}</p>")
        else:
            result.append(stripped)
            i += 1

    if in_list:
        result.append("</ul>")
    if in_table:
        result.append(_convert_table(table_buf))

    return "".join(result)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    # 1. HTML-escape everything first so raw <...>, &, > in prose or code spans
    #    survive as literal text instead of being consumed as markup (Bug 4).
    text = _escape(text)

    # 2. Protect code spans before emphasis so that (a) * inside code is not
    #    treated as emphasis, and (b) emphasis can still wrap a run that begins
    #    with or consists of a code span (Bug 5). Placeholders contain no
    #    emphasis/link characters.
    codes: list[str] = []

    def _stash(m: "re.Match[str]") -> str:
        codes.append(m.group(1))
        return f"\x00CODE{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _stash, text)

    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Link-text group is [^\]]+ (not .+?) so it cannot swallow an intervening
    # ] and merge two adjacent links into one.
    text = re.sub(
        r"\[([^\]]+)\]\(#([^)]+)\)",
        r'<ac:link ac:anchor="\2"><ac:link-body>\1</ac:link-body></ac:link>',
        text,
    )
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)

    for idx, code in enumerate(codes):
        text = text.replace(f"\x00CODE{idx}\x00", f"<code>{code}</code>")
    return text


def _convert_code_block(lines: list[str], start: int) -> tuple[str, int]:
    lang_match = re.match(r"^```(\w+)?", lines[start])
    lang = lang_match.group(1) if lang_match and lang_match.group(1) else ""
    end = start + 1
    while end < len(lines) and not lines[end].strip().startswith("```"):
        end += 1
    code = "\n".join(lines[start + 1 : end])
    code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if lang:
        html = (
            f'<ac:structured-macro ac:name="code">'
            f'<ac:parameter ac:name="language">{lang}</ac:parameter>'
            f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>"
            f"</ac:structured-macro>"
        )
    else:
        html = f"<pre>{code}</pre>"
    return html, end + 1


def _split_row(row: str) -> list[str]:
    # Split on unescaped pipes only, then unescape \| -> | inside each cell so a
    # literal pipe (e.g. a `str \| None` type union) does not shred the row into
    # extra columns (Bug 2).
    parts = re.split(r"(?<!\\)\|", row)
    return [c.strip().replace("\\|", "|") for c in parts[1:-1]]


def _convert_table(table_lines: list[str]) -> str:
    if len(table_lines) < 2:
        return "\n".join(table_lines)
    html = ["<table><tbody>"]
    header_cells = _split_row(table_lines[0])
    html.append("<tr>")
    for c in header_cells:
        html.append(f"<th>{_inline(c)}</th>")
    html.append("</tr>")
    for row in table_lines[2:]:
        cells = _split_row(row)
        if cells:
            html.append("<tr>")
            for c in cells:
                html.append(f"<td>{_inline(c)}</td>")
            html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html)


def _convert_checkboxes(lines: list[str], start: int) -> tuple[str, int]:
    tasks = []
    i = start
    while i < len(lines):
        m = re.match(r"^- \[( |x|X)\] (.+)$", lines[i].strip())
        if not m:
            break
        status = "complete" if m.group(1).lower() == "x" else "incomplete"
        text = _inline(m.group(2))
        tasks.append(
            f"<ac:task><ac:task-status>{status}</ac:task-status>"
            f"<ac:task-body>{text}</ac:task-body></ac:task>"
        )
        i += 1
    return "<ac:task-list>" + "".join(tasks) + "</ac:task-list>", i
