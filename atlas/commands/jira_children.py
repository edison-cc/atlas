"""atlas jira children <KEY> -- list all child issues recursively."""

from atlas.config import get_story_points_field, warn_story_points_unconfigured


def register(subparser):
    p = subparser.add_parser("children", help="List child issues (recursive)")
    p.add_argument("key", help="Parent issue key (e.g. PROJ-123)")
    p.add_argument("--story-points", action="store_true",
                    help="Include story points column (requires story_points_field in config)")
    p.add_argument("--depth", type=int, default=2,
                    help="Max recursion depth (default: 2)")
    p.add_argument("--limit", type=int, default=100,
                    help="Max results per query (default: 100)")
    p.set_defaults(func=run)


def run(args, client):
    show_sp = args.story_points
    sp_field = get_story_points_field() if show_sp else None
    if show_sp and not sp_field:
        warn_story_points_unconfigured()
        show_sp = False
    all_issues = _collect_children(client, [args.key], args.depth, args.limit, sp_field)

    print(f"## Children of {args.key}: {len(all_issues)} issues")
    print()

    if not all_issues:
        print("No child issues found.")
        return

    if show_sp:
        print("| Key | Summary | SP | Status | Assignee | Parent |")
        print("|-----|---------|----|--------|----------|--------|")
    else:
        print("| Key | Summary | Status | Assignee | Parent |")
        print("|-----|---------|--------|----------|--------|")

    for issue in all_issues:
        key = issue.get("key", "")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        status = _name(fields.get("status"))
        assignee = _display_name(fields.get("assignee"))
        parent_key = _parent_key(fields)
        if show_sp:
            sp = _story_points(fields, sp_field)
            print(f"| {key} | {summary} | {sp} | {status} | {assignee} | {parent_key} |")
        else:
            print(f"| {key} | {summary} | {status} | {assignee} | {parent_key} |")


def _collect_children(client, parent_keys, depth, limit, sp_field):
    """BFS traversal: fetch children of parent_keys, recurse up to depth levels."""
    if depth <= 0 or not parent_keys:
        return []

    keys_csv = ", ".join(parent_keys)
    jql = f"parent in ({keys_csv}) ORDER BY key ASC"
    api_fields = "key,summary,status,assignee,parent"
    if sp_field:
        api_fields = f"{api_fields},{sp_field}"

    data = client.jira_get("search/jql", params={
        "jql": jql,
        "fields": api_fields,
        "maxResults": limit,
    })
    issues = data.get("issues", [])

    if not issues:
        return []

    child_keys = [i["key"] for i in issues]
    grandchildren = _collect_children(client, child_keys, depth - 1, limit, sp_field)
    return issues + grandchildren


def _name(obj):
    if not obj:
        return "—"
    return obj.get("name", "—")


def _display_name(obj):
    if not obj:
        return "unassigned"
    return obj.get("displayName", "unknown")


def _parent_key(fields):
    parent = fields.get("parent")
    if parent and isinstance(parent, dict):
        return parent.get("key", "—")
    return "—"


def _story_points(fields, sp_field):
    val = fields.get(sp_field)
    if val is None:
        return "—"
    return int(val) if val == int(val) else val
