"""atlas jira comment <KEY> <BODY> -- add a comment to a Jira issue."""

from atlas.output import print_json


def register(subparser):
    p = subparser.add_parser("comment", help="Add a comment to an issue")
    p.add_argument("key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("body", help="Comment text")
    p.add_argument("--json", action="store_true", help="Output the result as JSON")
    p.set_defaults(func=run)


def run(args, client):
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": args.body}],
                }
            ],
        }
    }
    data = client.jira_post(f"issue/{args.key}/comment", json_body=payload)
    if args.json:
        print_json(operation="jira.comment", key=args.key, comment_id=data.get("id"))
    else:
        print(f"Comment added to {args.key}")
