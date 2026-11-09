"""Compare matched Atlas and ACLI JSON reads without saving private fixtures."""

import argparse
import json
import platform
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.benchmark_latency import command_version, fmt_stats, run_cli


def commands(case, atlas, acli):
    kind = case["kind"]
    if kind == "page":
        return {
            "atlas": [[atlas, "conf", "get", case["id"], "--format", "storage", "--json"]],
            "acli": [[acli, "confluence", "page", "view", "--id", case["id"],
                      "--body-format", "storage", "--json"]],
        }
    names = case["fields"]
    if not isinstance(names, list) or not names or not all(isinstance(name, str) and name for name in names):
        raise ValueError("Case fields must be a nonempty list of field names")
    fields = ",".join(names)
    if kind == "issue":
        return {
            "atlas": [[atlas, "jira", "get", case["key"], "--fields", fields, "--json"]],
            "acli": [[acli, "jira", "workitem", "view", case["key"], "--fields", fields, "--json"]],
        }
    if kind == "search":
        if not 0 <= case["count"] <= case["limit"] or case["limit"] < 1:
            raise ValueError("Expected search count must be within the requested limit")
        limit = str(case["limit"])
        return {
            "atlas": [[atlas, "jira", "search", case["jql"], "--fields", fields, "--limit", limit, "--json"]],
            "acli": [[acli, "jira", "workitem", "search", "--jql", case["jql"], "--fields", fields,
                      "--limit", limit, "--json"]],
        }
    if kind == "bulk":
        keys = case["keys"]
        if not isinstance(keys, list) or not keys or not all(
            isinstance(key, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*-[0-9]+", key) for key in keys
        ) or len(set(keys)) != len(keys):
            raise ValueError("Bulk cases require distinct Jira issue keys")
        jql = f"key in ({', '.join(keys)})"
        return {
            "atlas_single": [[atlas, "jira", "get", key, "--fields", fields, "--json"] for key in keys],
            "atlas": [[atlas, "jira", "get", *keys, "--fields", fields, "--json"]],
            "acli": [[acli, "jira", "workitem", "search", "--jql", jql,
                      "--fields", fields, "--paginate", "--json"]],
        }
    raise ValueError("Case kind must be issue, search, page, or bulk")


def comparable(case, method, payloads):
    data = payloads[0]
    if method in ("atlas", "atlas_single") and any(row.get("schema_version") != 1 for row in payloads):
        raise ValueError("Atlas JSON schema version 1 is required")
    if case["kind"] == "page":
        if str(data["id"]) != case["id"]:
            raise ValueError("Unexpected page")
        body = data["body"]
        storage = body["value"] if method == "atlas" else body["storage"]["value"]
        if not storage:
            raise ValueError("Missing page content")
        return (str(data["id"]), data["title"], storage)
    if case["kind"] == "issue":
        if data["key"] != case["key"]:
            raise ValueError("Unexpected issue")
        rows = [data]
    elif case["kind"] == "search":
        rows = data["items"] if method == "atlas" else data
        if len(rows) != case["count"]:
            raise ValueError("Unexpected search result count")
    else:
        keys = case["keys"]
        if method == "atlas_single" or (method == "atlas" and len(keys) == 1):
            rows = payloads
        elif method == "atlas":
            if data["errors"]:
                raise ValueError("Incomplete bulk result")
            rows = data["items"]
        else:
            by_key = {row["key"]: row for row in data}
            if len(data) != len(keys) or set(by_key) != set(keys):
                raise ValueError("Unexpected ACLI issues")
            rows = [by_key[key] for key in keys]
        if [row["key"] for row in rows] != keys:
            raise ValueError("Unexpected issues or order")
    projected = []
    for row in rows:
        fields = {name: row["fields"][name] for name in case["fields"] if name != "key"}
        if "status" in fields:
            status = fields["status"]
            fields["status"] = {"id": status["id"], "name": status["name"]}
        if "comment" in fields:
            comments = fields["comment"]
            fields["comment"] = {
                "total": comments["total"],
                "comments": [
                    {key: comment[key] for key in ("id", "body", "created", "updated")}
                    for comment in comments["comments"]
                ],
            }
        projected.append((row["key"], row["id"], fields))
    return projected


def run_case(case, executables, runs, warmup):
    # Persist only safe labels, field names, and numeric samples.
    result = {key: case[key] for key in ("name", "kind", "fields", "limit", "count") if key in case}
    if case["kind"] == "bulk":
        result["count"] = len(case["keys"])
    methods = tuple(executables)
    result["samples"] = []
    for index in range(warmup + runs):
        offset = index % len(methods)
        order = methods[offset:] + methods[:offset]
        sample = {"phase": "warmup" if index < warmup else "measured", "iteration": index}
        responses = {}
        for method in order:
            try:
                outputs = [run_cli(command, []) for command in executables[method]]
                responses[method] = comparable(case, method, [json.loads(output) for _, output in outputs])
                sample[method] = {
                    "ms": round(sum(elapsed for elapsed, _ in outputs), 3),
                    "stdout_bytes": sum(len(output.encode("utf-8")) for _, output in outputs),
                }
            except (ValueError, TypeError, KeyError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
                sample[method] = {"error": type(error).__name__}
        sample["matched"] = len(responses) == len(methods) and all(
            responses[method] == responses["atlas"] for method in methods
        )
        result["samples"].append(sample)
    measured = [sample for sample in result["samples"] if sample["phase"] == "measured"]
    matched = [sample for sample in measured if sample["matched"]]
    mismatch_count = "mismatched_rounds" if case["kind"] == "bulk" else "mismatched_pairs"
    result[mismatch_count] = sum(
        not sample["matched"] and all("error" not in sample[method] for method in methods)
        for sample in measured
    )
    result["summary"] = {}
    for method in methods:
        summary = {
            "attempted": len(measured),
            "failed": sum("error" in sample[method] for sample in measured),
            "matched": len(matched),
        }
        if matched:
            summary.update(fmt_stats([sample[method]["ms"] for sample in matched]))
            summary["median_stdout_bytes"] = statistics.median(sample[method]["stdout_bytes"] for sample in matched)
        result["summary"][method] = summary
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path, help="Local JSON manifest")
    parser.add_argument("--atlas", default="atlas")
    parser.add_argument("--acli", default="acli")
    parser.add_argument("--atlas-revision", required=True, help="Source commit or tree ID")
    parser.add_argument("--output", required=True, type=Path, help="New results file")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=2)
    args = parser.parse_args()
    if args.runs < 1 or args.warmup < 0:
        parser.error("runs must be positive and warmup nonnegative")
    try:
        cases = json.loads(args.cases.read_text(encoding="utf-8"))
        if not isinstance(cases, list) or not cases or not all(
            isinstance(case, dict) and isinstance(case.get("name"), str) and case["name"].strip()
            for case in cases
        ):
            raise ValueError("Empty or invalid cases list")
        executable_pairs = [commands(case, args.atlas, args.acli) for case in cases]
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(f"Could not read cases ({type(error).__name__})")

    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "atlas": command_version([args.atlas, "--version"]),
        "atlas_revision": args.atlas_revision,
        "acli": command_version([args.acli, "--version"]),
        "runs": args.runs, "warmup": args.warmup, "cases": [],
    }
    with args.output.open("x", encoding="utf-8") as output:
        for case, executable_pair in zip(cases, executable_pairs):
            print(f"Measuring {case['name']}...", flush=True)
            result = run_case(case, executable_pair, args.runs, args.warmup)
            report["cases"].append(result)
            for method, summary in result["summary"].items():
                print(method, json.dumps(summary), flush=True)
        report["status"] = "complete" if all(
            case["summary"]["atlas"]["matched"] == args.runs for case in report["cases"]
        ) else "incomplete"
        json.dump(report, output, indent=2)
        output.write("\n")
    return int(report["status"] != "complete")


if __name__ == "__main__":
    sys.exit(main())
