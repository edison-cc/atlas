"""atlas jira create -- create a new Jira issue."""

import json

from atlas.adf import markdown_to_adf
from atlas.config import require_acceptance_criteria_field
from atlas.output import print_json


def register(subparser):
    p = subparser.add_parser("create", help="Create a new issue")
    p.add_argument("--project", required=True, help="Project key (e.g. PROJ)")
    p.add_argument("--type", required=True, dest="issue_type",
                    help="Issue type (e.g. Story, Bug, Task)")
    p.add_argument("--summary", required=True, help="Issue summary/title")
    p.add_argument("--description", default="", help="Markdown description")
    p.add_argument("--parent", help="Parent issue key (e.g. PROJ-100)")
    p.add_argument("--assignee", help="Assignee account ID or email")
    p.add_argument("--labels", help="Comma-separated labels")
    p.add_argument("--ac", help="Markdown acceptance criteria (requires acceptance_criteria_field in config)")
    p.add_argument("--fields", help="Additional fields as JSON object")
    p.add_argument("--json", action="store_true", help="Output the result as JSON")
    p.set_defaults(func=run)


def run(args, client):
    fields = {
        "project": {"key": args.project},
        "issuetype": {"name": args.issue_type},
        "summary": args.summary,
    }

    if args.description:
        fields["description"] = markdown_to_adf(args.description)

    if args.parent:
        fields["parent"] = {"key": args.parent}

    if args.assignee:
        fields["assignee"] = {"id": args.assignee}

    if args.labels:
        fields["labels"] = [l.strip() for l in args.labels.split(",")]

    if args.ac:
        fields[require_acceptance_criteria_field()] = markdown_to_adf(args.ac)

    if args.fields:
        extra = json.loads(args.fields)
        fields.update(extra)

    data = client.jira_post("issue", json_body={"fields": fields})

    if args.json:
        print_json(operation="jira.create", key=data.get("key"), id=data.get("id"))
    else:
        key = data.get("key", "unknown")
        print(f"Created {key}")
