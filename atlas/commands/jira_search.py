"""atlas jira search <JQL> -- search issues and display as Markdown table."""

from atlas.config import get_story_points_field, warn_story_points_unconfigured


def register(subparser):
    p = subparser.add_parser("search", help="Search issues with JQL")
    p.add_argument("jql", help="JQL query string")
    p.add_argument("--fields", default="key,summary,status,assignee,updated",
                    help="Comma-separated fields (default: key,summary,status,assignee,updated)")
    p.add_argument("--story-points", action="store_true",
                    help="Include story points column (requires story_points_field in config)")
    p.add_argument("--parent", action="store_true",
                    help="Include parent key column")
    p.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
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

    params = {
        "jql": args.jql,
        "fields": api_fields,
        "maxResults": args.limit,
    }
    data = client.jira_get("search/jql", params=params)

    issues = data.get("issues") or []
    showing = len(issues)
    total = data.get("total")
    has_more = bool(data.get("nextPageToken")) or data.get("isLast") is False
    if total is not None and total > showing:
        has_more = True
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
