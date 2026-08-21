"""atlas jira update <KEY> -- update an existing Jira issue."""

import json

from atlas.adf import markdown_to_adf

ACCEPTANCE_CRITERIA_FIELD = "customfield_10046"


def register(subparser):
    p = subparser.add_parser("update", help="Update an existing issue")
    p.add_argument("key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("--summary", help="New summary")
    p.add_argument("--description", help="New Markdown description")
    p.add_argument("--assignee", help="New assignee account ID")
    p.add_argument("--labels", help="Comma-separated labels (replaces existing)")
    p.add_argument("--ac", help="New Markdown acceptance criteria")
    p.add_argument("--fields", help="Additional fields as JSON object")
    p.set_defaults(func=run)


def run(args, client):
    fields = {}

    if args.summary:
        fields["summary"] = args.summary

    if args.description:
        fields["description"] = markdown_to_adf(args.description)

    if args.assignee:
        fields["assignee"] = {"id": args.assignee}

    if args.labels:
        fields["labels"] = [l.strip() for l in args.labels.split(",")]

    if args.ac:
        fields[ACCEPTANCE_CRITERIA_FIELD] = markdown_to_adf(args.ac)

    if args.fields:
        extra = json.loads(args.fields)
        fields.update(extra)

    if not fields:
        print("Nothing to update. Provide at least one of --summary, --description, --assignee, --labels, --ac, --fields.")
        return

    client.jira_put(f"issue/{args.key}", json_body={"fields": fields})
    print(f"Updated {args.key}")
