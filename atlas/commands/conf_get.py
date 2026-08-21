"""atlas conf get <PAGE-ID> -- get a Confluence page's content."""

import re


def register(subparser):
    p = subparser.add_parser("get", help="Get a Confluence page")
    p.add_argument("page_id", help="Numeric page ID")
    p.add_argument(
        "--format",
        choices=["md", "storage"],
        default="md",
        dest="fmt",
        help="Output format: md (readable, default) or storage (raw HTML)",
    )
    p.add_argument(
        "--comments", action="store_true", help="Include comments (default: off)"
    )
    p.set_defaults(func=run)


def _fetch_all_page_comments(client, page_id: str) -> list:
    """Load every comment on a page, paginating and flattening replies."""
    start = 0
    limit = 100
    out = []
    while True:
        data = client.confluence_get(
            f"content/{page_id}/child/comment",
            params={
                "start": start,
                "limit": limit,
                "expand": "body.storage,history,version,extensions.location",
                "depth": "all",
            },
        )
        results = data.get("results") or []
        out.extend(results)
        if len(results) < limit:
            break
        start += len(results)
    return out


def run(args, client):
    params = {"expand": "body.storage,version,space"}
    data = client.confluence_get(f"content/{args.page_id}", params=params)

    title = data.get("title", "")
    space = data.get("space", {}).get("key", "")
    version = data.get("version", {}).get("number", "")
    updated = data.get("version", {}).get("when", "")[:10]

    storage_body = data.get("body", {}).get("storage", {}).get("value", "")

    print(f"## {title}")
    print()
    print(f"- **Space**: {space} | **Version**: {version} | **Updated**: {updated}")
    print()

    if args.fmt == "storage":
        print(storage_body)
    else:
        print(_storage_to_text(storage_body))

    if args.comments:
        comments = _fetch_all_page_comments(client, args.page_id)
        if comments:
            print()
            print(f"### Comments ({len(comments)})")
            print()
            for c in comments:
                history = c.get("history", {}) or {}
                author = (history.get("createdBy", {}) or {}).get("displayName", "unknown")
                date = (history.get("createdDate", "") or "")[:10]
                location = c.get("extensions", {}).get("location", "")
                body = _storage_to_text(c.get("body", {}).get("storage", {}).get("value", ""))
                tag = f" [{location}]" if location == "inline" else ""
                print(f"**{author}** ({date}){tag}: {body}")


def _storage_to_text(html: str) -> str:
    """Best-effort conversion of Confluence storage format to readable text."""
    text = html

    text = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", lambda m: f"{'#' * int(m.group(1))} {m.group(2)}", text)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1", text, flags=re.DOTALL)
    text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text)
    text = re.sub(r"<em>(.*?)</em>", r"*\1*", text)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text)
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n", text, flags=re.DOTALL)

    text = re.sub(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?'
        r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>"
        r"</ac:structured-macro>",
        r"```\n\1\n```",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
