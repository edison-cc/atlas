"""Compare matched Atlas and ACLI JSON reads without saving private fixtures."""

import argparse
import json
import platform
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
            "atlas": [atlas, "conf", "get", case["id"], "--format", "storage", "--json"],
            "acli": [acli, "confluence", "page", "view", "--id", case["id"],
                     "--body-format", "storage", "--json"],
        }
    names = case["fields"]
    if not isinstance(names, list) or not names or not all(isinstance(name, str) and name for name in names):
        raise ValueError("Case fields must be a nonempty list of field names")
    fields = ",".join(names)
    if kind == "issue":
        return {
            "atlas": [atlas, "jira", "get", case["key"], "--fields", fields, "--json"],
            "acli": [acli, "jira", "workitem", "view", case["key"], "--fields", fields, "--json"],
        }
    if kind == "search":
        if not 0 <= case["count"] <= case["limit"] or case["limit"] < 1:
            raise ValueError("Expected search count must be within the requested limit")
        limit = str(case["limit"])
        return {
            "atlas": [atlas, "jira", "search", case["jql"], "--fields", fields, "--limit", limit, "--json"],
            "acli": [acli, "jira", "workitem", "search", "--jql", case["jql"], "--fields", fields,
                     "--limit", limit, "--json"],
        }
    raise ValueError("Case kind must be issue, search, or page")


def comparable(case, method, output):
    data = json.loads(output)
    if method == "atlas" and data.get("schema_version") != 1:
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
    else:
        rows = data["items"] if method == "atlas" else data
        if len(rows) != case["count"]:
            raise ValueError("Unexpected search result count")
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
    result["samples"] = []
    for index in range(warmup + runs):
        order = ("atlas", "acli") if index % 2 == 0 else ("acli", "atlas")
        sample = {"phase": "warmup" if index < warmup else "measured", "iteration": index}
        responses = {}
        for method in order:
            try:
                elapsed, output = run_cli(executables[method], [])
                responses[method] = comparable(case, method, output)
                sample[method] = {"ms": round(elapsed, 3), "stdout_bytes": len(output.encode("utf-8"))}
            except (ValueError, TypeError, KeyError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
                sample[method] = {"error": type(error).__name__}
        sample["matched"] = len(responses) == 2 and responses["atlas"] == responses["acli"]
        result["samples"].append(sample)
    measured = [sample for sample in result["samples"] if sample["phase"] == "measured"]
    matched = [sample for sample in measured if sample["matched"]]
    result["mismatched_pairs"] = sum(
        not sample["matched"] and all("error" not in sample[method] for method in ("atlas", "acli"))
        for sample in measured
    )
    result["summary"] = {}
    for method in ("atlas", "acli"):
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
