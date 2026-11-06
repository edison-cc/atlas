"""atlas jira get <KEY> -- show issue details as compact Markdown."""

from atlas.adf import adf_to_markdown
from atlas.config import get_acceptance_criteria_field, get_story_points_field


def issue_fields(
    requested: str | None,
    include_comments: bool,
    extra: list[str | None] | None = None,
) -> str:
    """Build the Jira fields list for an issue fetch.

    ``*navigable`` does not include comments on current Jira Cloud, so comments
    are requested explicitly. Configured custom fields are appended the same way.
    """
    if requested:
        fields = [part.strip() for part in requested.split(",") if part.strip()]
    else:
        fields = ["*navigable"]
    if include_comments and "comment" not in fields:
        fields.append("comment")
    for field_id in extra or []:
        if field_id and field_id not in fields:
            fields.append(field_id)
    return ",".join(fields)


def register(subparser):
    p = subparser.add_parser("get", help="Get issue details")
    p.add_argument("key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("--fields", help="Comma-separated fields to fetch")
    p.add_argument(
        "--comments", action="store_true", help="Include comments (default: off)"
    )
    p.set_defaults(func=run)


def run(args, client):
    sp_field = get_story_points_field()
    ac_field = get_acceptance_criteria_field()
    params = {
        "fields": issue_fields(args.fields, args.comments, [sp_field, ac_field]),
    }

    data = client.jira_get(f"issue/{args.key}", params=params)
    fields = data.get("fields", {})

    summary = fields.get("summary", "")
    status = _name(fields.get("status"))
    issue_type = _name(fields.get("issuetype"))
    priority = _name(fields.get("priority"))
    assignee = _display_name(fields.get("assignee"))
    reporter = _display_name(fields.get("reporter"))
    labels = ", ".join(fields.get("labels", [])) or "none"
    created = _date(fields.get("created"))
    updated = _date(fields.get("updated"))

    story_points = _story_points(fields, sp_field)
    sprint = _extract_sprint(fields)
    parent_key, parent_type = _extract_parent(fields)

    print(f"## {args.key}: {summary}")
    print()
    print(f"- **Status**: {status} | **Type**: {issue_type} | **Priority**: {priority}")
    print(f"- **Assignee**: {assignee} | **Reporter**: {reporter}")
    if story_points is not None:
        print(f"- **Story Points**: {story_points}")
    if labels != "none":
        print(f"- **Labels**: {labels}")
    if sprint:
        print(f"- **Sprint**: {sprint}")
    if parent_key:
        print(f"- **Parent**: {parent_key} ({parent_type})")
    print(f"- **Created**: {created} | **Updated**: {updated}")

    desc_adf = fields.get("description")
    if desc_adf:
        desc_text = adf_to_markdown(desc_adf)
        if desc_text:
            print()
            print("### Description")
            print()
            print(desc_text)

    ac_adf = fields.get(ac_field) if ac_field else None
    if ac_adf:
        ac_text = adf_to_markdown(ac_adf)
        if ac_text:
            print()
            print("### Acceptance Criteria")
            print()
            print(ac_text)

    if args.comments:
        comments = fields.get("comment", {}).get("comments", [])
        if comments:
            print()
            print(f"### Comments ({len(comments)})")
            print()
            for c in comments:
                author = _display_name(c.get("author"))
                date = _date(c.get("created"))
                body = adf_to_markdown(c.get("body"))
                print(f"**{author}** ({date}): {body}")


def _name(obj):
    if not obj:
        return "—"
    return obj.get("name", "—")


def _display_name(obj):
    if not obj:
        return "unassigned"
    return obj.get("displayName", obj.get("name", "unknown"))


def _date(iso_str):
    if not iso_str:
        return "—"
    return iso_str[:10]


def _story_points(fields, sp_field):
    if not sp_field:
        return None
    val = fields.get(sp_field)
    if val is None:
        return None
    return int(val) if val == int(val) else val


def _extract_sprint(fields):
    sprint = fields.get("sprint")
    if sprint and isinstance(sprint, dict):
        return sprint.get("name", "")
    for key, val in fields.items():
        if "sprint" in key.lower() and isinstance(val, list) and val:
            last = val[-1]
            if isinstance(last, dict):
                return last.get("name", "")
    return ""


def _extract_parent(fields):
    parent = fields.get("parent")
    if parent and isinstance(parent, dict):
        key = parent.get("key", "")
        type_name = parent.get("fields", {}).get("issuetype", {}).get("name", "")
        return key, type_name
    return "", ""
