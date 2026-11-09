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
                    help="Max results per Jira request (default: 100)")
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
    """Read every page in each level before moving down to its children."""
    fields = ["key", "summary", "status", "assignee", "parent"]
    if sp_field:
        fields.append(sp_field)

    issues = []
    seen_keys = set(parent_keys)
    for _ in range(depth):
        if not parent_keys:
            break
        keys_csv = ", ".join(parent_keys)
        query = {
            "jql": f"parent in ({keys_csv}) ORDER BY key ASC",
            "fields": fields,
            "maxResults": limit,
        }
        parent_keys = []
        for issue in _iter_search_issues(client, query):
            key = issue["key"]
            if key not in seen_keys:
                seen_keys.add(key)
                parent_keys.append(key)
                issues.append(issue)
    return issues


def _iter_search_issues(client, query):
    seen = set()
    while True:
        # A wide level can produce more JQL than fits in a GET URL.
        page = client.jira_post("search/jql", json_body=query)
        yield from page.get("issues") or []
        token = page.get("nextPageToken")
        if page.get("isLast") is True or (not token and page.get("isLast") is not False):
            return
        if not token or token in seen:
            raise SystemExit("Jira returned an invalid pagination token. Results are incomplete.")
        seen.add(token)
        query = {**query, "nextPageToken": token}


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
