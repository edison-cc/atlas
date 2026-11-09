"""atlas jira get <KEY> [<KEY> ...] -- show issue details."""

import sys

from atlas.adf import adf_to_markdown
from atlas.config import get_acceptance_criteria_field, get_story_points_field
from atlas.output import pagination, print_json


_BULK_SIZE = 100


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
    p.add_argument("keys", nargs="+", metavar="KEY", help="One or more issue keys or IDs")
    p.add_argument("--fields", help="Comma-separated fields to fetch")
    p.add_argument("--json", action="store_true", help="Output structured JSON")
    p.add_argument(
        "--comments", action="store_true",
        help="Include comments from the issue response and show how many were returned",
    )
    p.set_defaults(func=run)


def run(args, client):
    sp_field = get_story_points_field()
    ac_field = get_acceptance_criteria_field()
    fields = issue_fields(args.fields, args.comments, [sp_field, ac_field])
    if len(args.keys) == 1:
        key = args.keys[0]
        data = client.jira_get(f"issue/{key}", params={"fields": fields})
        result = _issue_result(data, key, args.comments)
        if args.json:
            print_json(**result)
        else:
            _print_issue(result, key, sp_field, ac_field)
        return

    items, errors = _fetch_bulk(client, args.keys, fields.split(","), args.comments)
    if args.json:
        print_json(items=items, errors=errors)
    else:
        for index, item in enumerate(items):
            if index:
                print()
            _print_issue(item, item["key"], sp_field, ac_field)
    if errors:
        for error in errors:
            print(f'{error["input"]}: {error["message"]}', file=sys.stderr)
        raise SystemExit(1)


def _fetch_bulk(client, keys, fields, include_comments):
    by_input = {}
    for key in keys:
        by_input.setdefault(key.casefold(), key)
    unique = list(by_input.values())
    issues = {}
    messages = {}
    for start in range(0, len(unique), _BULK_SIZE):
        response = client.jira_post("issue/bulkfetch", json_body={
            "issueIdsOrKeys": unique[start:start + _BULK_SIZE],
            "fields": fields,
        })
        for issue in response.get("issues") or []:
            issues[issue["key"].casefold()] = issue
            issues[str(issue["id"])] = issue
        for error in response.get("issueErrors") or []:
            if error.get("id") is not None and error.get("errorMessage"):
                messages[str(error["id"])] = error["errorMessage"]

    items, errors = [], []
    for key in keys:
        identifier = key.casefold()
        if identifier in issues:
            items.append(_issue_result(issues[identifier], key, include_comments))
        else:
            message = messages.get(identifier, "Jira did not return an issue for this key or ID.")
            errors.append({"input": key, "message": message})
    return items, errors


def _issue_result(data, requested_key, include_comments):
    fields = data.get("fields", {})
    result = {"key": data.get("key", requested_key), "id": data.get("id"), "fields": fields}
    if include_comments:
        comment_page = fields.get("comment") or {}
        count = len(comment_page.get("comments") or [])
        total = comment_page.get("total")
        result["comments_pagination"] = pagination(count, total, count < total if total is not None else None)
    return result


def _print_issue(result, display_key, sp_field, ac_field):
    fields = result["fields"]
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

    print(f"## {display_key}: {summary}")
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

    if "comments_pagination" in result:
        info = result["comments_pagination"]
        comment_count = info["returned"]
        comment_total = info["total"]
        comments = (fields.get("comment") or {}).get("comments") or []
        count_label = (
            f"{comment_count} of {comment_total} shown"
            if comment_total is not None else f"{comment_count} shown, total unknown"
        )
        print(f"\n### Comments ({count_label})\n")
        for comment in comments:
            author = _display_name(comment.get("author"))
            date = _date(comment.get("created"))
            body = adf_to_markdown(comment.get("body"))
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
