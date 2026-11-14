"""atlas jira search <JQL> -- search issues and display as Markdown table."""

from atlas.config import get_story_points_field, warn_story_points_unconfigured
from atlas.jira_pagination import has_next_search_page, iter_search_pages
from atlas.output import pagination, print_json


_PAGINATED_PAGE_SIZE = 100


def register(subparser):
    p = subparser.add_parser("search", help="Search issues with JQL")
    p.add_argument("jql", help="JQL query string")
    p.add_argument("--fields", default="key,summary,status,assignee,updated",
                    help="Comma-separated fields (default: key,summary,status,assignee,updated)")
    p.add_argument("--story-points", action="store_true",
                    help="Include story points column (requires story_points_field in config)")
    p.add_argument("--parent", action="store_true",
                    help="Include parent key column")
    p.add_argument("--limit", type=int,
                    help="Max results (default: 20 on a single page, unlimited with --paginate)")
    p.add_argument("--paginate", action="store_true", help="Fetch all pages, up to --limit if specified")
    p.add_argument("--json", action="store_true", help="Output structured JSON")
    p.set_defaults(func=run)


def run(args, client):
    show_sp = args.story_points
    show_parent = args.parent
    sp_field = get_story_points_field()
    if show_sp and not sp_field:
        warn_story_points_unconfigured()
        show_sp = False
    api_fields = args.fields
    if show_sp and sp_field not in [part.strip() for part in api_fields.split(",")]:
        api_fields = f"{api_fields},{sp_field}"
    if show_parent and "parent" not in api_fields.split(","):
        api_fields = f"{api_fields},parent"

    if args.paginate:
        issues, total, has_more = _paginated_search(client, args.jql, api_fields, args.limit)
    else:
        data = client.jira_get("search/jql", params={
            "jql": args.jql,
            "fields": api_fields,
            "maxResults": 20 if args.limit is None else args.limit,
        })
        issues = data.get("issues") or []
        total = data.get("total")
        has_more = has_next_search_page(data)
    showing = len(issues)
    has_more = has_more or (total is not None and total > showing)
    if args.json:
        print_json(
            items=[{"key": issue.get("key"), "id": issue.get("id"), "fields": issue.get("fields", {})}
                   for issue in issues],
            pagination=pagination(showing, total, has_more),
        )
        return
    if total is not None and total > showing:
        print(f"## Jira: {total} results (showing {showing})")
    elif has_more:
        print(f"## Jira: {showing} results shown (more available)")
    else:
        print(f"## Jira: {showing} results")
    print()

    if not issues:
        print("No results on this page." if has_more else "No results.")
        return

    header, sep = _build_header(show_sp, show_parent)
    print(header)
    print(sep)

    for issue in issues:
        key = issue.get("key", "")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        status = _name(fields.get("status"))
        assignee = _display_name(fields.get("assignee"))
        updated = _date(fields.get("updated"))
        cols = [key, summary]
        if show_sp:
            cols.append(str(_story_points(fields, sp_field)))
        cols.extend([status, assignee])
        if show_parent:
            cols.append(_parent_key(fields))
        cols.append(updated)
        print("| " + " | ".join(cols) + " |")


def _paginated_search(client, jql, fields, limit):
    if limit is not None and limit < 1:
        raise SystemExit("--limit must be positive with --paginate.")
    query = {
        "jql": jql,
        "fields": [field.strip() for field in fields.split(",") if field.strip()],
        "maxResults": min(limit, _PAGINATED_PAGE_SIZE) if limit is not None else _PAGINATED_PAGE_SIZE,
    }
    issues = []
    total = None
    for page in iter_search_pages(client, query):
        issues.extend(page.get("issues") or [])
        if page.get("total") is not None:
            total = page["total"]
        if limit is not None and len(issues) >= limit:
            has_more = len(issues) > limit or has_next_search_page(page)
            return issues[:limit], total, has_more

    if total is not None and total > len(issues):
        raise SystemExit("Jira ended pagination before returning the reported total. Results are incomplete.")
    return issues, total, False


def _build_header(show_sp, show_parent):
    cols = ["Key", "Summary"]
    if show_sp:
        cols.append("SP")
    cols.extend(["Status", "Assignee"])
    if show_parent:
        cols.append("Parent")
    cols.append("Updated")
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    return header, sep


def _parent_key(fields):
    parent = fields.get("parent")
    if parent and isinstance(parent, dict):
        return parent.get("key", "—")
    return "—"


def _name(obj):
    if not obj:
        return "—"
    return obj.get("name", "—")


def _display_name(obj):
    if not obj:
        return "unassigned"
    return obj.get("displayName", "unknown")


def _date(iso_str):
    if not iso_str:
        return "—"
    return iso_str[:10]


def _story_points(fields, sp_field):
    if not sp_field:
        return "—"
    val = fields.get(sp_field)
    if val is None:
        return "—"
    return int(val) if val == int(val) else val
