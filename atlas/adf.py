"""Bidirectional conversion between Atlassian Document Format (ADF) and Markdown.

Jira Cloud v3 returns descriptions and comments as ADF -- a recursive JSON
tree with node types like paragraph, heading, text, bulletList, codeBlock, etc.

- ``adf_to_markdown`` walks the ADF tree and emits compact Markdown.
- ``markdown_to_adf`` parses a Markdown string into an ADF document node.
"""

import re


def adf_to_markdown(doc: dict | None) -> str:
    """Convert a top-level ADF document node to Markdown string."""
    if not doc or doc.get("type") != "doc":
        return ""
    parts = []
    for node in doc.get("content", []):
        parts.append(_render_node(node))
    return "\n".join(parts).strip()


def _render_node(node: dict, list_prefix: str = "") -> str:
    t = node.get("type", "")

    if t == "paragraph":
        return _render_children(node)

    if t == "heading":
        level = node.get("attrs", {}).get("level", 1)
        text = _render_children(node)
        return f"{'#' * level} {text}"

    if t == "text":
        return _apply_marks(node.get("text", ""), node.get("marks", []))

    if t == "hardBreak":
        return "\n"

    if t == "bulletList":
        items = []
        for child in node.get("content", []):
            items.append(_render_list_item(child, "- "))
        return "\n".join(items)

    if t == "orderedList":
        items = []
        for i, child in enumerate(node.get("content", []), 1):
            items.append(_render_list_item(child, f"{i}. "))
        return "\n".join(items)

    if t == "listItem":
        return _render_children(node)

    if t == "codeBlock":
        lang = node.get("attrs", {}).get("language", "")
        code = _render_children(node)
        return f"```{lang}\n{code}\n```"

    if t == "blockquote":
        inner = _render_children(node)
        return "\n".join(f"> {line}" for line in inner.split("\n"))

    if t == "rule":
        return "---"

    if t == "mention":
        return f"@{node.get('attrs', {}).get('text', 'unknown')}"

    if t in ("inlineCard", "blockCard"):
        url = node.get("attrs", {}).get("url", "")
        return url

    if t == "mediaSingle":
        for child in node.get("content", []):
            if child.get("type") == "media":
                alt = child.get("attrs", {}).get("alt", "")
                fname = child.get("attrs", {}).get("__fileName", "attachment")
                return f"[{alt or fname}]"
        return "[attachment]"

    if t == "table":
        return _render_table(node)

    if t == "emoji":
        return node.get("attrs", {}).get("shortName", "")

    if t == "panel":
        return _render_children(node)

    return _render_children(node)


def _render_children(node: dict) -> str:
    parts = []
    for child in node.get("content", []):
        parts.append(_render_node(child))
    return "".join(parts)


def _render_list_item(node: dict, prefix: str) -> str:
    text = _render_children(node)
    lines = text.split("\n")
    result = [f"{prefix}{lines[0]}"]
    for line in lines[1:]:
        result.append(f"  {line}")
    return "\n".join(result)


def _apply_marks(text: str, marks: list) -> str:
    for mark in marks:
        mt = mark.get("type", "")
        if mt == "strong":
            text = f"**{text}**"
        elif mt == "em":
            text = f"*{text}*"
        elif mt == "code":
            text = f"`{text}`"
        elif mt == "link":
            href = mark.get("attrs", {}).get("href", "")
            text = f"[{text}]({href})"
        elif mt == "strike":
            text = f"~~{text}~~"
    return text


def _render_table(node: dict) -> str:
    rows = []
    for row_node in node.get("content", []):
        if row_node.get("type") != "tableRow":
            continue
        cells = []
        for cell_node in row_node.get("content", []):
            cells.append(_render_children(cell_node).replace("|", "\\|").strip())
        rows.append(cells)

    if not rows:
        return ""

    lines = ["| " + " | ".join(rows[0]) + " |"]
    lines.append("|" + "|".join("---" for _ in rows[0]) + "|")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown -> ADF
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_ORDERED_RE = re.compile(r"^(\s*)\d+\.\s+(.*)")
_BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)")
_RULE_RE = re.compile(r"^---+\s*$")
_CODE_FENCE_RE = re.compile(r"^```(\w*)\s*$")
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\|[\s:]*-{3,}[\s:]*(\|[\s:]*-{3,}[\s:]*)*\|\s*$")
_INLINE_RE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|\*(.+?)\*")


def markdown_to_adf(text: str) -> dict:
    """Convert a Markdown string to an ADF document node."""
    if not text or not text.strip():
        return _empty_doc()
    blocks = _parse_md_blocks(text.split("\n"))
    return {"type": "doc", "version": 1, "content": blocks or [_empty_para()]}


def _empty_doc() -> dict:
    return {"type": "doc", "version": 1, "content": [_empty_para()]}


def _empty_para() -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": " "}]}


def _parse_md_blocks(lines: list[str]) -> list[dict]:
    blocks: list[dict] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        if _RULE_RE.match(line):
            blocks.append({"type": "rule"})
            i += 1
            continue

        m = _CODE_FENCE_RE.match(line)
        if m:
            lang = m.group(1)
            code_lines: list[str] = []
            i += 1
            while i < n and not lines[i].rstrip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # skip closing fence
            node: dict = {"type": "codeBlock", "content": []}
            if lang:
                node["attrs"] = {"language": lang}
            if code_lines:
                node["content"] = [{"type": "text", "text": "\n".join(code_lines)}]
            blocks.append(node)
            continue

        m = _HEADING_RE.match(line)
        if m:
            blocks.append({
                "type": "heading",
                "attrs": {"level": len(m.group(1))},
                "content": _parse_md_inline(m.group(2)),
            })
            i += 1
            continue

        if _ORDERED_RE.match(line):
            node, i = _parse_md_list(lines, i, "orderedList")
            blocks.append(node)
            continue

        if _BULLET_RE.match(line):
            node, i = _parse_md_list(lines, i, "bulletList")
            blocks.append(node)
            continue

        if _TABLE_ROW_RE.match(line):
            node, i = _parse_md_table(lines, i)
            blocks.append(node)
            continue

        para_parts: list[str] = []
        while i < n and lines[i].strip():
            if (_HEADING_RE.match(lines[i]) or _ORDERED_RE.match(lines[i])
                    or _BULLET_RE.match(lines[i]) or _RULE_RE.match(lines[i])
                    or _CODE_FENCE_RE.match(lines[i])
                    or _TABLE_ROW_RE.match(lines[i])):
                break
            para_parts.append(lines[i].strip())
            i += 1
        if para_parts:
            blocks.append({
                "type": "paragraph",
                "content": _parse_md_inline(" ".join(para_parts)),
            })

    return blocks


def _parse_md_list(
    lines: list[str], start: int, list_type: str,
) -> tuple[dict, int]:
    items: list[dict] = []
    i, n = start, len(lines)
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    item_re = _ORDERED_RE if list_type == "orderedList" else _BULLET_RE

    while i < n:
        line = lines[i]

        if not line.strip():
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and item_re.match(lines[j]):
                ni = len(lines[j]) - len(lines[j].lstrip())
                if ni == base_indent:
                    i = j
                    continue
            break

        indent = len(line) - len(line.lstrip())
        if indent < base_indent:
            break

        m = item_re.match(line)
        if m and indent == base_indent:
            item_content: list[dict] = [
                {"type": "paragraph", "content": _parse_md_inline(m.group(2))},
            ]
            i += 1

            while i < n and lines[i].strip():
                ni = len(lines[i]) - len(lines[i].lstrip())
                if ni <= base_indent:
                    break
                if _BULLET_RE.match(lines[i]):
                    nested, i = _parse_md_list(lines, i, "bulletList")
                    item_content.append(nested)
                elif _ORDERED_RE.match(lines[i]):
                    nested, i = _parse_md_list(lines, i, "orderedList")
                    item_content.append(nested)
                else:
                    break

            items.append({"type": "listItem", "content": item_content})
        else:
            break

    return {"type": list_type, "content": items}, i


def _parse_md_table(
    lines: list[str], start: int,
) -> tuple[dict, int]:
    """Parse consecutive Markdown table rows into an ADF table node."""
    i, n = start, len(lines)
    raw_rows: list[list[str]] = []

    while i < n:
        m = _TABLE_ROW_RE.match(lines[i])
        if not m:
            break
        if _TABLE_SEP_RE.match(lines[i]):
            i += 1
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        raw_rows.append(cells)
        i += 1

    adf_rows: list[dict] = []
    for idx, row in enumerate(raw_rows):
        cell_type = "tableHeader" if idx == 0 else "tableCell"
        adf_cells = [
            {
                "type": cell_type,
                "content": [{"type": "paragraph", "content": _parse_md_inline(cell)}],
            }
            for cell in row
        ]
        adf_rows.append({"type": "tableRow", "content": adf_cells})

    return {"type": "table", "content": adf_rows}, i


def _parse_md_inline(text: str) -> list[dict]:
    if not text:
        return [{"type": "text", "text": " "}]

    nodes: list[dict] = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            nodes.append({"type": "text", "text": text[pos:m.start()]})
        if m.group(1) is not None:
            nodes.append({"type": "text", "text": m.group(1),
                          "marks": [{"type": "code"}]})
        elif m.group(2) is not None:
            nodes.append({"type": "text", "text": m.group(2),
                          "marks": [{"type": "strong"}]})
        elif m.group(3) is not None:
            nodes.append({"type": "text", "text": m.group(3),
                          "marks": [{"type": "em"}]})
        pos = m.end()

    if pos < len(text):
        nodes.append({"type": "text", "text": text[pos:]})

    return nodes or [{"type": "text", "text": text}]
