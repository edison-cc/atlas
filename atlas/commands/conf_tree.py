"""atlas conf tree <SPACE-KEY> -- show page hierarchy for a space."""

from atlas.confluence_pagination import iter_results
from atlas.output import print_json

def register(subparser):
    p = subparser.add_parser("tree", help="Show page tree for a space")
    p.add_argument("space_key", help="Space key (e.g. DEV)")
    p.add_argument("--depth", type=int, default=3, help="Max depth (default: 3)")
    p.add_argument("--json", action="store_true", help="Output structured JSON")
    p.set_defaults(func=run)


def run(args, client):
    params = {
        "type": "page",
        "spaceKey": args.space_key,
        "expand": "ancestors",
        "limit": 200,
    }
    pages = {page["id"]: page for page in iter_results(client, "content", params)}

    tree, detached = _build_tree(pages.values())
    roots = _limit_tree(tree, args.depth)
    detached = _limit_tree(detached, args.depth)
    if args.json:
        print_json(space_key=args.space_key, fetched_count=len(pages), depth=args.depth,
                   roots=roots, detached=detached)
        return

    print(f"## Page tree: {args.space_key} ({len(pages)} pages)")
    print()

    _print_tree(roots)
    if detached:
        print("\n### Pages with unavailable parents")
        _print_tree(detached)


def _build_tree(pages):
    """Build a nested tree structure from flat page list with ancestors."""
    by_id = {}
    roots = []
    detached = []

    for page in pages:
        pid = page["id"]
        by_id[pid] = {
            "id": pid,
            "title": page.get("title", ""),
            "children": [],
        }

    for page in pages:
        pid = page["id"]
        ancestors = page.get("ancestors", [])
        if ancestors:
            parent_id = ancestors[-1]["id"]
            if parent_id in by_id:
                by_id[parent_id]["children"].append(by_id[pid])
            else:
                detached.append(by_id[pid])
        else:
            roots.append(by_id[pid])

    return roots, detached


def _limit_tree(nodes, depth):
    if depth <= 0:
        return []
    return [
        {**node, "children": _limit_tree(node["children"], depth - 1)}
        for node in sorted(nodes, key=lambda node: node["title"])
    ]


def _print_tree(nodes, indent=0):
    for node in nodes:
        prefix = "  " * indent + ("- " if indent > 0 else "")
        print(f"{prefix}{node['title']} ({node['id']})")
        _print_tree(node["children"], indent + 1)
