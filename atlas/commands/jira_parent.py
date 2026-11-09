"""atlas jira parent <KEY> -- show ancestor chain up the hierarchy."""

from atlas.output import print_json


def register(subparser):
    p = subparser.add_parser("parent", help="Show ancestor chain (walks up)")
    p.add_argument("key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("--depth", type=int, default=5,
                    help="Max levels to traverse (default: 5)")
    p.add_argument("--json", action="store_true", help="Output structured JSON")
    p.set_defaults(func=run)


def run(args, client):
    api_fields = "summary,status,issuetype,parent"
    chain = []
    current_key = args.key

    for depth in range(args.depth + 1):
        data = client.jira_get(f"issue/{current_key}", params={"fields": api_fields})
        fields = data.get("fields", {})
        parent = fields.get("parent")
        parent_key = parent.get("key") if isinstance(parent, dict) else None
        chain.append({
            "key": current_key,
            "id": data.get("id"),
            "parent_key": parent_key,
            "depth": depth,
            "fields": fields,
        })
        if not parent_key:
            break
        current_key = parent_key

    if args.json:
        print_json(root_key=args.key, items=chain)
        return

    print(f"## Ancestors of {args.key}")
    print()

    for item in chain:
        indent = "  " * item["depth"]
        fields = item["fields"]
        summary = fields.get("summary", "")
        issue_type = _name(fields.get("issuetype"))
        status = _name(fields.get("status"))
        print(f"{indent}- {item['key']}: {summary} ({issue_type}) — {status}")


def _name(obj):
    if not obj:
        return "—"
    return obj.get("name", "—")
