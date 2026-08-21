"""atlas jira transitions <KEY> -- list available transitions for an issue."""


def register(subparser):
    p = subparser.add_parser("transitions", help="List available transitions")
    p.add_argument("key", help="Issue key (e.g. PROJ-123)")
    p.set_defaults(func=run)


def run(args, client):
    data = client.jira_get(f"issue/{args.key}/transitions")
    transitions = data.get("transitions", [])

    print(f"## Transitions for {args.key}")
    print()

    if not transitions:
        print("No transitions available.")
        return

    print("| ID | Name | To Status |")
    print("|----|------|-----------|")
    for t in transitions:
        tid = t.get("id", "")
        name = t.get("name", "")
        to_status = t.get("to", {}).get("name", "")
        print(f"| {tid} | {name} | {to_status} |")
