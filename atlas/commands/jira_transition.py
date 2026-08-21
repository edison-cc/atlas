"""atlas jira transition <KEY> <ID> -- transition an issue to a new status."""


def register(subparser):
    p = subparser.add_parser("transition", help="Transition issue to new status")
    p.add_argument("key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("transition_id", help="Transition ID (use 'atlas jira transitions' to list)")
    p.add_argument("--comment", help="Optional comment to add with the transition")
    p.set_defaults(func=run)


def run(args, client):
    payload = {"transition": {"id": args.transition_id}}

    if args.comment:
        payload["update"] = {
            "comment": [
                {
                    "add": {
                        "body": {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": args.comment}
                                    ],
                                }
                            ],
                        }
                    }
                }
            ]
        }

    client.jira_post(f"issue/{args.key}/transitions", json_body=payload)
    print(f"Transitioned {args.key}")
