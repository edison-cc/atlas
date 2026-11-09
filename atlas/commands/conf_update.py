"""atlas conf update <PAGE-ID> -- update a Confluence page."""

import sys

from atlas.commands.conf_publish import _markdown_to_storage
from atlas.output import print_json


def register(subparser):
    p = subparser.add_parser("update", help="Update a Confluence page")
    p.add_argument("page_id", help="Numeric page ID")
    p.add_argument("--title", help="New page title")
    p.add_argument("--body", help="New page body in Markdown (converted to storage format; use --raw to skip). Read from stdin if '-'")
    p.add_argument("--raw", action="store_true", help="Body is already Confluence storage-format XHTML; skip markdown conversion")
    p.add_argument("--minor", action="store_true", help="Mark as minor edit")
    p.add_argument("--json", action="store_true", help="Output the result as JSON")
    p.set_defaults(func=run)


def run(args, client):
    current = client.confluence_get(
        f"content/{args.page_id}", params={"expand": "version,body.storage"}
    )

    version = current["version"]["number"]
    title = args.title or current["title"]

    body_value = current["body"]["storage"]["value"]
    if args.body == "-":
        body_value = sys.stdin.read()
    elif args.body:
        body_value = args.body

    if args.body and not args.raw:
        body_value = _markdown_to_storage(body_value)

    payload = {
        "version": {"number": version + 1, "minorEdit": args.minor},
        "title": title,
        "type": "page",
        "body": {
            "storage": {
                "value": body_value,
                "representation": "storage",
            }
        },
    }

    client.confluence_put(f"content/{args.page_id}", json_body=payload)
    if args.json:
        print_json(operation="conf.update", id=args.page_id, title=title, version=version + 1)
    else:
        print(f"Updated page {args.page_id}: {title}")
