"""Render Confluence storage markup as readable Markdown."""

import re
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser


_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


@dataclass
class _Element:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def elements(self, *tags):
        return [child for child in self.children if isinstance(child, _Element) and child.tag in tags]


class _StorageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = _Element("")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = self._append_element(tag, attrs)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._append_element(tag, attrs)

    def _append_element(self, tag, attrs):
        node = _Element(tag, dict(attrs))
        self.stack[-1].children.append(node)
        return node

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)

    def unknown_decl(self, text):
        if text.startswith("CDATA["):
            self.handle_data(text[6:])


def storage_to_markdown(storage: str) -> str:
    parser = _StorageParser()
    parser.feed(storage)
    parser.close()
    return _markdown(parser.root).strip()


def _plain_text(node):
    if isinstance(node, str):
        return node
    if node.tag == "br":
        return "\n"
    return "".join(_plain_text(child) for child in node.children)


def _backticks(text, minimum):
    longest = max((len(match) for match in re.findall(r"`+", text)), default=0)
    return "`" * max(minimum, longest + 1)


def _code_block(text, language=""):
    fence = _backticks(text, 3)
    if not re.fullmatch(r"[\w+-]*", language):
        language = ""
    separator = "" if text.endswith("\n") else "\n"
    return f"\n{fence}{language}\n{text}{separator}{fence}\n"


def _markdown(node):
    if isinstance(node, str):
        return node
    tag = node.tag
    if tag in ("script", "style", "ac:parameter"):
        return ""
    if tag == "table":
        return _table(node)
    if tag == "pre":
        return _code_block(_plain_text(node))
    if tag == "ac:structured-macro" and node.attrs.get("ac:name") == "code":
        bodies = node.elements("ac:plain-text-body")
        if bodies:
            language = next(
                (_plain_text(param) for param in node.elements("ac:parameter")
                 if param.attrs.get("ac:name") == "language"),
                "",
            )
            return _code_block(_plain_text(bodies[0]), language)
    if tag == "code":
        code = _plain_text(node)
        fence = _backticks(code, 1)
        padding = " " if "`" in code or (code.startswith(" ") and code.endswith(" ")) else ""
        return f"{fence}{padding}{code}{padding}{fence}"
    if tag in ("ul", "ol"):
        items = []
        for index, item in enumerate(node.elements("li"), 1):
            marker = f"{index}." if tag == "ol" else "-"
            indent = " " * (len(marker) + 1)
            value = _markdown(item).strip().replace("\n", "\n" + indent)
            items.append(f"{marker} {value}")
        return "\n" + "\n".join(items) + "\n"

    body = "".join(_markdown(child) for child in node.children)
    if tag in _HEADINGS:
        return f"\n{'#' * int(tag[1])} {body.strip()}\n"
    if tag in ("p", "div"):
        return f"\n{body.strip()}\n" if body.strip() else ""
    if tag in ("strong", "b"):
        return f"**{body}**"
    if tag in ("em", "i"):
        return f"*{body}*"
    if tag == "br":
        return "\n"
    if tag == "hr":
        return "\n\n---\n\n"
    if tag == "a":
        return _link(body, node.attrs.get("href"))
    if tag == "ac:link":
        if node.elements("ri:page", "ri:blog-post", "ri:attachment"):
            return _html(node)
        urls = node.elements("ri:url")
        if urls:
            return _link(body.strip(), urls[0].attrs.get("ri:value"))
        anchor = node.attrs.get("ac:anchor")
        if anchor:
            return _link(body.strip() or anchor, f"#{anchor}")
    return body


def _link(body, href):
    if not href:
        return body
    destination = f"<{href}>" if any(character in href for character in " ()") else href
    return f"[{body or href}]({destination})"


def _html(node):
    if isinstance(node, str):
        return escape(node, quote=False)
    attrs = "".join(
        f' {key}="{escape(value, quote=True)}"' for key, value in node.attrs.items() if value is not None
    )
    if node.tag in _VOID:
        return f"<{node.tag}{attrs} />"
    body = "".join(_html(child) for child in node.children)
    return f"<{node.tag}{attrs}>{body}</{node.tag}>"


def _table(node):
    rows = []
    for section in node.elements("thead", "tbody", "tfoot", "tr"):
        rows.extend(section.elements("tr") if section.tag != "tr" else [section])
    cells = [row.elements("th", "td") for row in rows]
    columns = max(map(len, cells), default=0)
    if not columns:
        return ""
    # Markdown pipe tables cannot represent merged cells or block code.
    if any(
        cell.attrs.get("rowspan", "1") != "1" or cell.attrs.get("colspan", "1") != "1"
        for row in cells for cell in row
    ):
        return f"\n\n{_html(node)}\n\n"
    lines = []
    for row in cells:
        values = []
        for cell in row:
            value = _markdown(cell).strip()
            if re.search(r"(?m)^(?:`{3,}|\|)", value):
                return f"\n\n{_html(node)}\n\n"
            values.append(re.sub(r"\s*\n+\s*", "<br>", value).replace("|", r"\|"))
        values.extend([""] * (columns - len(values)))
        lines.append("| " + " | ".join(values) + " |")
    if not any(cell.tag == "th" for cell in cells[0]):
        lines.insert(0, "| " + " | ".join([""] * columns) + " |")
    lines.insert(1, "| " + " | ".join(["---"] * columns) + " |")
    return "\n\n" + "\n".join(lines) + "\n\n"
