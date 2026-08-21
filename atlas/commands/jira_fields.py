"""atlas jira fields -- discover Jira field IDs and names."""


def register(subparser):
    p = subparser.add_parser("fields", help="List Jira fields (for custom field discovery)")
    p.add_argument("--search", default=None,
                    help="Case-insensitive filter on field name")
    p.set_defaults(func=run)


def run(args, client):
    data = client.jira_get("field")

    fields = sorted(data, key=lambda f: f.get("name", ""))

    if args.search:
        term = args.search.lower()
        fields = [f for f in fields if term in f.get("name", "").lower()]

    print(f"## Jira fields: {len(fields)} results")
    print()

    if not fields:
        print("No matching fields.")
        return

    print("| ID | Name | Type | Custom |")
    print("|----|------|------|--------|")
    for f in fields:
        fid = f.get("id", "")
        name = f.get("name", "")
        schema = f.get("schema", {})
        ftype = schema.get("type", f.get("type", "—"))
        custom = "yes" if f.get("custom", False) else "no"
        print(f"| {fid} | {name} | {ftype} | {custom} |")
