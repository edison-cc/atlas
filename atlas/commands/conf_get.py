"""atlas conf get <PAGE-ID> -- get a Confluence page's content."""

from atlas.confluence_pagination import iter_results
from atlas.confluence_storage import storage_to_markdown


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
    return list(iter_results(client, f"content/{page_id}/child/comment", {
        "limit": 100,
        "expand": "body.storage,history,version,extensions.location",
        "depth": "all",
    }))


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
        print(storage_to_markdown(storage_body))

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
                body = storage_to_markdown(c.get("body", {}).get("storage", {}).get("value", ""))
                tag = f" [{location}]" if location == "inline" else ""
                print(f"**{author}** ({date}){tag}: {body}")
