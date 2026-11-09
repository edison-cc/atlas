"""atlas jira children <KEY> -- list all child issues recursively."""

from atlas.config import get_story_points_field, warn_story_points_unconfigured
from atlas.jira_pagination import iter_search_pages
from atlas.output import print_json


def register(subparser):
    p = subparser.add_parser("children", help="List child issues (recursive)")
    p.add_argument("key", help="Parent issue key (e.g. PROJ-123)")
    p.add_argument("--story-points", action="store_true",
                    help="Include story points column (requires story_points_field in config)")
    p.add_argument("--depth", type=int, default=2,
                    help="Max recursion depth (default: 2)")
    p.add_argument("--limit", type=int, default=100,
                    help="Max results per Jira request (default: 100)")
    p.add_argument("--json", action="store_true", help="Output structured JSON")
    p.set_defaults(func=run)


def run(args, client):
    show_sp = args.story_points
    sp_field = get_story_points_field() if show_sp else None
    if show_sp and not sp_field:
        warn_story_points_unconfigured()
        show_sp = False
    all_issues = _collect_children(client, [args.key], args.depth, args.limit, sp_field)
    if args.json:
        print_json(root_key=args.key, items=all_issues)
        return

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
        parent_key = issue["parent_key"] or "—"
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
    for level in range(1, depth + 1):
        if not parent_keys:
            break
        keys_csv = ", ".join(parent_keys)
        query = {
            "jql": f"parent in ({keys_csv}) ORDER BY key ASC",
            "fields": fields,
            "maxResults": limit,
        }
        parent_keys = []
        for page in iter_search_pages(client, query):
            for issue in page.get("issues") or []:
                key = issue["key"]
                if key not in seen_keys:
                    seen_keys.add(key)
                    parent_keys.append(key)
                    issue_fields = issue.get("fields", {})
                    parent = issue_fields.get("parent")
                    issues.append({
                        "key": key,
                        "id": issue.get("id"),
                        "parent_key": parent.get("key") if isinstance(parent, dict) else None,
                        "depth": level,
                        "fields": issue_fields,
                    })
    return issues


def _name(obj):
    if not obj:
        return "—"
    return obj.get("name", "—")


def _display_name(obj):
    if not obj:
        return "unassigned"
    return obj.get("displayName", "unknown")


def _story_points(fields, sp_field):
    val = fields.get(sp_field)
    if val is None:
        return "—"
    return int(val) if val == int(val) else val
