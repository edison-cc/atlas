"""Compare real Mermaid rendering in two Atlas source checkouts."""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from benchmarks.benchmark_latency import command_version, fmt_stats


_DIAGRAMS = (
    "flowchart LR\n    Client --> API --> Queue --> Worker",
    "sequenceDiagram\n    Worker->>Queue: Read job\n    Worker->>Storage: Save result",
    "flowchart TD\n    Error --> Retry{Retryable?}\n    Retry -->|Yes| Queue\n    Retry -->|No| DeadLetter",
    "flowchart LR\n    Worker --> Metrics --> Dashboard",
)
_CASES = {
    "repeated": (0, 1, 0, 1),
    "distinct": (0, 1, 2, 3),
}
_RENDER_LINE = re.compile(r"Rendering diagram [0-9]+\.\.\.")
_ATTACHMENT_REF = re.compile(r'<ri:attachment ri:filename="([^"]+)"')


def write_fixture(path, diagrams):
    sections = ["# Queue worker design", "The API queues work for asynchronous processing."]
    for index, diagram in enumerate(diagrams, 1):
        sections.append(f"## Design view {index}\n\n```mermaid\n{_DIAGRAMS[diagram]}\n```")
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def run_preview(tree, fixture, env):
    command = [
        sys.executable, "-m", "atlas.cli", "conf", "publish", "123", str(fixture),
        "--title", "Queue worker design", "--dry-run", "--json",
    ]
    started = time.perf_counter()
    process = subprocess.run(
        command, cwd=tree, env=env, capture_output=True, text=True, encoding="utf-8", timeout=270,
    )
    elapsed = (time.perf_counter() - started) * 1000
    if process.returncode:
        raise RuntimeError(process.stderr.strip())
    return json.loads(process.stdout), {
        "ms": round(elapsed, 3),
        "renders": sum(bool(_RENDER_LINE.fullmatch(line)) for line in process.stderr.splitlines()),
    }


def preview_structure(preview, diagrams, *, reused):
    body = preview["body"]
    refs = _ATTACHMENT_REF.findall(body["value"])
    if len(refs) != len(diagrams) or list(dict.fromkeys(refs)) != preview["attachments"]:
        raise ValueError("Preview must preserve all diagram references and list their attachments")
    if len(set(zip(refs, diagrams))) != len(set(refs)):
        raise ValueError("Distinct sources in the fixture must have distinct attachments")
    if reused and len(set(refs)) != len(set(diagrams)):
        raise ValueError("Repeated sources in the candidate must share one attachment")
    return {
        **preview, "attachments": len(diagrams),
        "body": {**body, "value": _ATTACHMENT_REF.sub('<ri:attachment ri:filename="DIAGRAM"', body["value"])},
    }


def compare_case(trees, fixture, diagrams, env, runs, warmup):
    samples = []
    for index in range(runs + warmup):
        order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
        sample = {"phase": "warmup" if index < warmup else "measured"}
        previews, structures = {}, {}
        for method in order:
            previews[method], sample[method] = run_preview(trees[method], fixture, env)
            reused = method == "candidate"
            expected_renders = len(set(diagrams)) if reused else len(diagrams)
            if sample[method]["renders"] != expected_renders:
                raise ValueError(f"Unexpected number of renderer starts for {method}")
            structures[method] = preview_structure(previews[method], diagrams, reused=reused)
        if structures["candidate"] != structures["baseline"]:
            raise ValueError("Previews must match after replacing content-addressed attachment names")
        sample["identical_preview"] = previews["baseline"] == previews["candidate"]
        samples.append(sample)
        print(f"  {sample['phase']} {index + 1}: {sample['baseline']['renders']} -> "
              f"{sample['candidate']['renders']} renders", flush=True)

    measured = [sample for sample in samples if sample["phase"] == "measured"]
    return {
        "diagram_blocks": len(diagrams),
        "unique_sources": len(set(diagrams)),
        "samples": samples,
        "summary": {
            method: {
                **fmt_stats([sample[method]["ms"] for sample in measured]),
                "renders_per_run": sorted({sample[method]["renders"] for sample in measured}),
            }
            for method in trees
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline Atlas Git checkout")
    parser.add_argument("--candidate", type=Path, default=Path.cwd(), help="Candidate Atlas Git checkout")
    parser.add_argument("--browser", type=Path, required=True, help="Chrome or Chromium executable")
    parser.add_argument("--output", type=Path, required=True, help="New JSON report")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    args = parser.parse_args()
    renderer = shutil.which("mmdc")
    if not renderer or not args.browser.is_file() or not os.access(args.browser, os.X_OK):
        parser.error("mmdc must be on PATH and --browser must be executable")
    if args.runs < 1 or args.warmup < 0:
        parser.error("runs must be positive and warmup nonnegative")
    trees = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    revisions = {}
    for method, tree in trees.items():
        subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "atlas"], cwd=tree, check=True)
        revisions[method] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tree, text=True).strip()
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "mermaid_cli": command_version([renderer, "--version"]),
        "browser": command_version([str(args.browser.resolve()), "--version"]),
        "revisions": revisions,
        "runs": args.runs,
        "warmup": args.warmup,
        "cases": {},
    }
    env = {**os.environ, "PUPPETEER_EXECUTABLE_PATH": str(args.browser.resolve())}
    with args.output.open("x", encoding="utf-8") as output, TemporaryDirectory() as directory:
        fixture = Path(directory) / "design.md"
        for name, diagrams in _CASES.items():
            print(f"Measuring {name} diagram sources...", flush=True)
            write_fixture(fixture, diagrams)
            report["cases"][name] = compare_case(trees, fixture, diagrams, env, args.runs, args.warmup)
        json.dump(report, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
