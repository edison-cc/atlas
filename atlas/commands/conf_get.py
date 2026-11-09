"""atlas conf get <PAGE-ID> -- get a Confluence page's content."""

from atlas.confluence_pagination import iter_results
from atlas.confluence_storage import storage_to_markdown
from atlas.output import print_json


def register(subparser):
    p = subparser.add_parser("get", help="Get a Confluence page")
    p.add_argument("page_id", help="Numeric page ID")
    p.add_argument("--json", action="store_true", help="Output structured JSON")
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
    updated = data.get("version", {}).get("when") or ""

    storage_body = data.get("body", {}).get("storage", {}).get("value", "")
    body = storage_body if args.fmt == "storage" else storage_to_markdown(storage_body)
    comments = [_format_comment(comment) for comment in _fetch_all_page_comments(client, args.page_id)] if args.comments else []

    if args.json:
        payload = {
            "id": data.get("id", args.page_id), "title": title, "space_key": space,
            "version": version, "updated": updated, "body": {"format": args.fmt, "value": body},
        }
        if args.comments:
            payload["comments"] = comments
        print_json(**payload)
        return

    print(f"## {title}")
    print()
    print(f"- **Space**: {space} | **Version**: {version} | **Updated**: {updated[:10]}")
    print()

    print(body)
    if comments:
        print(f"\n### Comments ({len(comments)})\n")
        for comment in comments:
            tag = " [inline]" if comment["location"] == "inline" else ""
            print(f'**{comment["author"]}** ({comment["created"][:10]}){tag}: {comment["body"]}')


def _format_comment(comment):
    history = comment.get("history") or {}
    return {
        "id": comment.get("id"),
        "author": (history.get("createdBy") or {}).get("displayName", "unknown"),
        "created": history.get("createdDate") or "",
        "location": comment.get("extensions", {}).get("location", ""),
        "body": storage_to_markdown(comment.get("body", {}).get("storage", {}).get("value", "")),
    }
