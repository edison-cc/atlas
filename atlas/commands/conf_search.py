"""atlas conf search <QUERY> -- search Confluence pages."""


def register(subparser):
    p = subparser.add_parser("search", help="Search Confluence pages")
    p.add_argument("query", help="Search text or CQL query")
    p.add_argument("--space", help="Limit to a specific space key")
    p.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
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

    for r in results:
        content = r.get("content", r)
        title = content.get("title", r.get("title", ""))
        space = content.get("space", {}).get("key", "—") if isinstance(content.get("space"), dict) else "—"
        ctype = content.get("type", "—")
        updated = r.get("lastModified", content.get("version", {}).get("when", ""))[:10]
        page_id = content.get("id", "")
        print(f"| {title} ({page_id}) | {space} | {ctype} | {updated} |")
