"""atlas conf tree <SPACE-KEY> -- show page hierarchy for a space."""


def register(subparser):
    p = subparser.add_parser("tree", help="Show page tree for a space")
    p.add_argument("space_key", help="Space key (e.g. DEV)")
    p.add_argument("--depth", type=int, default=3, help="Max depth (default: 3)")
    p.set_defaults(func=run)


def run(args, client):
    params = {
        "type": "page",
        "spaceKey": args.space_key,
        "expand": "ancestors",
        "limit": 200,
    }
    data = client.confluence_get("content", params=params)
    pages = data.get("results", [])

    print(f"## Page tree: {args.space_key} ({len(pages)} pages)")
    print()

    tree = _build_tree(pages)
    _print_tree(tree, max_depth=args.depth)


def _build_tree(pages):
    """Build a nested tree structure from flat page list with ancestors."""
    by_id = {}
    roots = []

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
                roots.append(by_id[pid])
        else:
            roots.append(by_id[pid])

    return roots


def _print_tree(nodes, indent=0, max_depth=3):
    if indent >= max_depth:
        return
    for node in sorted(nodes, key=lambda n: n["title"]):
        prefix = "  " * indent + ("- " if indent > 0 else "")
        print(f"{prefix}{node['title']} ({node['id']})")
        _print_tree(node["children"], indent + 1, max_depth)
