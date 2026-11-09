"""atlas conf search <QUERY> -- search Confluence pages."""

from atlas.output import pagination, print_json


def register(subparser):
    p = subparser.add_parser("search", help="Search Confluence pages")
    p.add_argument("query", help="Search text or CQL query")
    p.add_argument("--space", help="Limit to a specific space key")
    p.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    p.add_argument("--json", action="store_true", help="Output structured JSON")
    p.set_defaults(func=run)


def run(args, client):
    cql = args.query
    if not any(op in cql for op in ["=", "~", "!", ">"]):
        cql = f'siteSearch ~ "{cql}"'
    if args.space:
        cql += f' AND space.key = "{args.space}"'

    params = {"cql": cql, "limit": args.limit}
    data = client.confluence_get("search", params=params)

    results = data.get("results") or []
    total = data.get("totalSize")
    has_more = bool(data.get("_links", {}).get("next")) or (total is not None and total > len(results))
    items = [_page_summary(result) for result in results]

    if args.json:
        print_json(items=items, pagination=pagination(len(items), total, has_more))
        return

    if total is not None and (not has_more or total > len(results)):
        print(f"## Confluence: {total} results (showing {len(results)})")
    elif has_more:
        print(f"## Confluence: {len(results)} results shown (more available)")
    else:
        print(f"## Confluence: {len(results)} results")
    print()

    if not results:
        print("No results on this page." if has_more else "No results.")
        return

    print("| Title | Space | Type | Updated |")
    print("|-------|-------|------|---------|")

    for item in items:
        print(f"| {item['title']} ({item['id']}) | {item['space_key'] or '—'} | "
              f"{item['type'] or '—'} | {(item['updated'] or '')[:10]} |")


def _page_summary(result):
    content = result.get("content", result)
    space = content.get("space")
    return {
        "id": content.get("id", ""),
        "title": content.get("title", result.get("title", "")),
        "space_key": space.get("key") if isinstance(space, dict) else None,
        "type": content.get("type"),
        "updated": result.get("lastModified", (content.get("version") or {}).get("when")),
    }
