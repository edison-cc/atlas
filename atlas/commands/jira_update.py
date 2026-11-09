"""atlas jira update <KEY> -- update an existing Jira issue."""

import json

from atlas.adf import markdown_to_adf
from atlas.config import require_acceptance_criteria_field
from atlas.output import print_json


def register(subparser):
    p = subparser.add_parser("update", help="Update an existing issue")
    p.add_argument("key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("--summary", help="New summary")
    p.add_argument("--description", help="New Markdown description")
    p.add_argument("--assignee", help="New assignee account ID")
    p.add_argument("--labels", help="Comma-separated labels (replaces existing)")
    p.add_argument("--ac", help="New Markdown acceptance criteria (requires acceptance_criteria_field in config)")
    p.add_argument("--fields", help="Additional fields as JSON object")
    p.add_argument("--json", action="store_true", help="Output the result as JSON")
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
        fields[require_acceptance_criteria_field()] = markdown_to_adf(args.ac)

    if args.fields:
        extra = json.loads(args.fields)
        fields.update(extra)

    changed = bool(fields)
    if changed:
        client.jira_put(f"issue/{args.key}", json_body={"fields": fields})

    if args.json:
        print_json(operation="jira.update", key=args.key, changed=changed)
    elif changed:
        print(f"Updated {args.key}")
    else:
        print("Nothing to update. Provide at least one of --summary, --description, --assignee, --labels, --ac, --fields.")
