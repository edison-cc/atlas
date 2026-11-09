"""Atlas CLI entry point -- dispatches to command modules."""

import argparse
import sys
from collections import defaultdict

from requests import HTTPError

from atlas import __version__
from atlas.commands import discover_commands
from atlas.config import load_config
from atlas.client import AtlassianClient


def main():
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Compact CLI for Jira and Confluence Cloud",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    group_parsers = {}
    subparsers = parser.add_subparsers(dest="group")

    groups = defaultdict(list)
    for prefix, module in discover_commands():
        groups[prefix].append(module)

    group_labels = {"jira": "Jira commands", "conf": "Confluence commands"}

    for prefix, modules in sorted(groups.items()):
        label = group_labels.get(prefix, f"{prefix} commands")
        group_parser = subparsers.add_parser(prefix, help=label)
        group_sub = group_parser.add_subparsers(dest="command")
        group_parsers[prefix] = group_sub

        for module in modules:
            module.register(group_sub)

    args = parser.parse_args()

    if not args.group:
        parser.print_help()
        sys.exit(1)

    if not getattr(args, "command", None):
        # Print help for the group (e.g., "atlas jira")
        for action in subparsers._group_actions:
            for choice_key, choice_parser in action.choices.items():
                if choice_key == args.group:
                    choice_parser.print_help()
                    sys.exit(1)
        sys.exit(1)

    if args.group == "conf" and args.command == "publish" and args.dry_run:
        args.func(args, None)
        return

    try:
        args.func(args, AtlassianClient(load_config()))
    except HTTPError as error:
        print(error, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
