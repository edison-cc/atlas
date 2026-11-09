"""atlas conf create -- create a new Confluence page."""

import sys

from atlas.output import print_json


def register(subparser):
    p = subparser.add_parser("create", help="Create a new Confluence page")
    p.add_argument("--space", required=True, help="Space key (e.g. DEV)")
    p.add_argument("--title", required=True, help="Page title")
    p.add_argument("--body", default="", help="Page body (read from stdin if '-')")
    p.add_argument("--parent", help="Parent page ID")
    p.add_argument("--json", action="store_true", help="Output the result as JSON")
    p.set_defaults(func=run)


def run(args, client):
    body = args.body
    if body == "-":
        body = sys.stdin.read()

    payload = {
        "type": "page",
        "title": args.title,
        "space": {"key": args.space},
        "body": {
            "storage": {
                "value": body,
                "representation": "storage",
            }
        },
    }

    if args.parent:
        payload["ancestors"] = [{"id": args.parent}]

    data = client.confluence_post("content", json_body=payload)

    if args.json:
        print_json(operation="conf.create", id=data.get("id"), title=args.title)
    else:
        page_id = data.get("id", "unknown")
        print(f"Created page {page_id}: {args.title}")
