"""atlas jira parent <KEY> -- show ancestor chain up the hierarchy."""


def register(subparser):
    p = subparser.add_parser("parent", help="Show ancestor chain (walks up)")
    p.add_argument("key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("--depth", type=int, default=5,
                    help="Max levels to traverse (default: 5)")
    p.set_defaults(func=run)


def run(args, client):
    api_fields = "summary,status,issuetype,parent"
    chain = []
    current_key = args.key

    for _ in range(args.depth + 1):
        data = client.jira_get(f"issue/{current_key}", params={"fields": api_fields})
        fields = data.get("fields", {})
        chain.append({
            "key": current_key,
            "summary": fields.get("summary", ""),
            "type": _name(fields.get("issuetype")),
            "status": _name(fields.get("status")),
        })
        parent = fields.get("parent")
        if not parent or not isinstance(parent, dict):
            break
        current_key = parent.get("key", "")
        if not current_key:
            break

    print(f"## Ancestors of {args.key}")
    print()

    for depth, item in enumerate(chain):
        indent = "  " * depth
        print(f"{indent}- {item['key']}: {item['summary']} ({item['type']}) — {item['status']}")


def _name(obj):
    if not obj:
        return "—"
    return obj.get("name", "—")
