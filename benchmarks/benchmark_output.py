#!/usr/bin/env python3
"""Measure reviewed UTF-8 output captures; optional exact tokenizer counts."""
import argparse
from importlib.metadata import version
import hashlib
import json
from pathlib import Path


def compare(manifest, root, encoding=None):
    cases = []
    totals = {}
    names = set()
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("Manifest must be a nonempty list")
    for case in manifest:
        name = case["name"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Case names must be nonempty and unique")
        names.add(name)
        expected = case["expected"]
        if not isinstance(expected, list) or not expected or not all(isinstance(v, str) and v for v in expected):
            raise ValueError("Each case needs required content strings")
        files = case["files"]
        if not {"atlas", "mcp"}.issubset(files):
            raise ValueError("Each case needs atlas and mcp captures")
        if totals and set(files) != set(totals):
            raise ValueError("Every case must have the same comparison sources")
        counts = {}
        for source, path in files.items():
            data = (root / path).read_bytes()
            text = data.decode("utf-8")
            if not text.strip() or any(value not in text for value in expected):
                raise ValueError(f"{name}/{source}: missing required content")
            metrics = {"chars": len(text), "utf8_bytes": len(data)}
            if encoding is not None:
                metrics["tokens"] = len(encoding.encode(text, disallowed_special=()))
            counts[source] = {**metrics, "sha256": hashlib.sha256(data).hexdigest()}
            subtotal = totals.setdefault(source, {key: 0 for key in metrics})
            for key, value in metrics.items():
                subtotal[key] += value
        cases.append({"name": name, "counts": counts})
    reductions = {source: {key: 100 * (1 - totals["atlas"][key] / value)
                          for key, value in metrics.items() if value}
                  for source, metrics in totals.items() if source != "atlas"}
    return {"cases": cases, "totals": totals, "atlas_reduction_percent": reductions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--encoding", help="Optional tiktoken encoding; requires tiktoken")
    args = parser.parse_args()
    try:
        encoding = None
        if args.encoding:
            import tiktoken
            encoding = tiktoken.get_encoding(args.encoding)
        report = compare(json.loads(args.manifest.read_text(encoding="utf-8")), args.manifest.parent, encoding)
        report["tokenizer"] = None if encoding is None else {"encoding": args.encoding, "library": "tiktoken", "version": version("tiktoken")}
        print(json.dumps(report, indent=2, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        parser.exit(1, f"Output comparison failed: {exc}\n")


if __name__ == "__main__":
    main()
