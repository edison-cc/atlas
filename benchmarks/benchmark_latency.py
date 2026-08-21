#!/usr/bin/env python3
"""Latency benchmark: Atlas CLI vs Docker MCP.

Measures wall-clock time for 5 Atlassian operations through both
Atlas CLI (subprocess) and Docker MCP (JSON-RPC over stdio gateway).

CLI timing uses subprocess.run() directly, which captures process startup
(~80 ms) and API call latency but does NOT include Cursor's Shell tool
sandbox overhead (~1.6-2.0 s per invocation). In real agent usage, CLI
commands go through the Shell tool sandbox, so actual per-call latency
is ~2 s higher than what this benchmark reports. MCP's CallMcpTool
bypasses the Shell sandbox, so MCP timings here match real agent usage.

This benchmark targets Docker MCP (ephemeral containers). HTTP and stdio
MCP servers have different overhead profiles — see LATENCY.md
"Scope and Limitations" for details.

Usage:
    python benchmark_latency.py              # run both CLI and MCP
    python benchmark_latency.py --cli-only   # run CLI only
    python benchmark_latency.py --runs 10    # 10 iterations per operation
"""

import argparse
import json
import os
import queue
import statistics
import subprocess
import sys
import threading
import time

OPERATIONS = [
    {
        "name": "Jira Get Issue",
        "cli": ["atlas", "jira", "get", "PROJ-123"],
        "mcp_tool": "jira_get_issue",
        "mcp_args": {"issue_key": "PROJ-123"},
        "schema_file": "jira_get_issue.json",
    },
    {
        "name": "Jira Search (5 issues)",
        "cli": ["atlas", "jira", "search", "updated >= -7d", "--limit", "5"],
        "mcp_tool": "jira_search",
        "mcp_args": {"jql": "updated >= -7d", "limit": 5},
        "schema_file": "jira_search.json",
    },
    {
        "name": "Jira Transitions",
        "cli": ["atlas", "jira", "transitions", "PROJ-123"],
        "mcp_tool": "jira_get_transitions",
        "mcp_args": {"issue_key": "PROJ-123"},
        "schema_file": "jira_get_transitions.json",
    },
    {
        "name": "Confluence Get Page",
        "cli": ["atlas", "conf", "get", "987923264"],
        "mcp_tool": "confluence_get_page",
        "mcp_args": {"page_id": "987923264"},
        "schema_file": "confluence_get_page.json",
    },
    {
        "name": "Confluence Search",
        "cli": ["atlas", "conf", "search", "design", "--limit", "5"],
        "mcp_tool": "confluence_search",
        "mcp_args": {"query": "design", "limit": 5},
        "schema_file": "confluence_search.json",
    },
]


def find_schema_dir():
    """Locate the MCP tool descriptor directory."""
    candidates = []
    import glob

    for pattern in glob.glob(
        os.path.expanduser("~/.cursor/projects/*/mcps/user-MCP_DOCKER/tools")
    ):
        candidates.append(pattern)
    for d in candidates:
        if os.path.isdir(d):
            return d
    return None


# ---------------------------------------------------------------------------
# Atlas CLI timing
# ---------------------------------------------------------------------------


def time_cli(cmd, runs):
    """Time an atlas CLI command, return list of elapsed ms."""
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        subprocess.run(cmd, capture_output=True, text=True)
        times.append((time.perf_counter() - start) * 1000)
    return times


# ---------------------------------------------------------------------------
# MCP gateway (JSON-RPC over stdio)
# ---------------------------------------------------------------------------


class McpGateway:
    """Communicates with `docker mcp gateway run` over stdio."""

    def __init__(self, timeout=30):
        self._msg_id = 0
        self._responses: queue.Queue = queue.Queue()
        self._timeout = timeout

        self.proc = subprocess.Popen(
            ["docker", "mcp", "gateway", "run"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

        # MCP handshake
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "benchmark", "version": "1.0"},
            },
        )
        self._notify("notifications/initialized", {})

    # -- I/O plumbing -------------------------------------------------------

    def _read_loop(self):
        """Read from gateway stdout, handle both newline-delimited JSON and
        Content-Length framed messages (LSP-style)."""
        buf = b""
        while True:
            byte = self.proc.stdout.read(1)
            if not byte:
                break
            buf += byte
            if byte == b"\n":
                line = buf.strip()
                buf = b""
                if not line:
                    continue
                if line.startswith(b"Content-Length:"):
                    length = int(line.split(b":")[1])
                    # consume the blank line after the header
                    while True:
                        hdr = self.proc.stdout.readline()
                        if hdr.strip() == b"":
                            break
                    body = self.proc.stdout.read(length)
                    self._handle_message(body)
                else:
                    self._handle_message(line)

    def _handle_message(self, raw: bytes):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if "id" in msg and ("result" in msg or "error" in msg):
            self._responses.put(msg)

    def _next_id(self):
        self._msg_id += 1
        return self._msg_id

    def _send(self, obj: dict):
        payload = json.dumps(obj) + "\n"
        self.proc.stdin.write(payload.encode())
        self.proc.stdin.flush()

    # -- public API ---------------------------------------------------------

    def request(self, method, params, timeout=None):
        timeout = timeout or self._timeout
        msg_id = self._next_id()
        self._send(
            {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        )
        deadline = time.monotonic() + timeout
        stash = []
        while time.monotonic() < deadline:
            try:
                resp = self._responses.get(timeout=0.5)
            except queue.Empty:
                continue
            if resp.get("id") == msg_id:
                for s in stash:
                    self._responses.put(s)
                return resp
            stash.append(resp)
        for s in stash:
            self._responses.put(s)
        raise TimeoutError(f"No response for {method} (id={msg_id})")

    def _notify(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def call_tool(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def time_mcp(gateway, tool_name, arguments, runs):
    """Time an MCP tool call through the running gateway."""
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        gateway.call_tool(tool_name, arguments)
        times.append((time.perf_counter() - start) * 1000)
    return times


# ---------------------------------------------------------------------------
# Schema read overhead
# ---------------------------------------------------------------------------


def time_schema_reads(schema_dir, runs):
    """Time reading each MCP schema JSON file from disk."""
    results = {}
    for op in OPERATIONS:
        path = os.path.join(schema_dir, op["schema_file"])
        if not os.path.exists(path):
            continue
        times = []
        for _ in range(runs):
            start = time.perf_counter()
            with open(path) as f:
                f.read()
            times.append((time.perf_counter() - start) * 1000)
        results[op["schema_file"]] = {"times": times, "size": os.path.getsize(path)}
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def fmt_stats(times):
    return {
        "median": statistics.median(times),
        "mean": statistics.mean(times),
        "min": min(times),
        "max": max(times),
    }


def print_section(title, rows, cols):
    """Print a markdown table."""
    print(f"\n## {title}\n")
    print("| " + " | ".join(cols) + " |")
    print("| " + " | ".join("---" for _ in cols) + " |")
    for row in rows:
        print("| " + " | ".join(str(c) for c in row) + " |")


def main():
    parser = argparse.ArgumentParser(description="Latency benchmark")
    parser.add_argument("--runs", type=int, default=5, help="Iterations per operation")
    parser.add_argument(
        "--cli-only", action="store_true", help="Skip Docker MCP measurement"
    )
    args = parser.parse_args()

    runs = args.runs
    print(f"# Latency Benchmark Results\n")
    print(f"Date: {time.strftime('%Y-%m-%d')}")
    print(f"Runs per operation: {runs}\n")

    # ---- Atlas CLI --------------------------------------------------------
    print("## Atlas CLI Execution Latency\n")
    print("| Operation | Median (ms) | Mean (ms) | Min (ms) | Max (ms) |")
    print("| --- | --- | --- | --- | --- |")
    cli_results = {}
    for op in OPERATIONS:
        print(f"  timing {op['name']}...", end="", file=sys.stderr, flush=True)
        times = time_cli(op["cli"], runs)
        s = fmt_stats(times)
        cli_results[op["name"]] = s
        print(
            f"| {op['name']} | {s['median']:.0f} | {s['mean']:.0f}"
            f" | {s['min']:.0f} | {s['max']:.0f} |"
        )
        print(f" {s['median']:.0f} ms", file=sys.stderr)

    # ---- Docker MCP -------------------------------------------------------
    mcp_results = None
    if not args.cli_only:
        print("\n## Docker MCP Execution Latency\n")
        try:
            print("Starting MCP gateway...", file=sys.stderr, flush=True)
            gateway = McpGateway(timeout=60)
            print("Gateway ready.\n", file=sys.stderr, flush=True)

            print("| Operation | Median (ms) | Mean (ms) | Min (ms) | Max (ms) |")
            print("| --- | --- | --- | --- | --- |")
            mcp_results = {}
            for op in OPERATIONS:
                print(
                    f"  timing {op['name']}...", end="", file=sys.stderr, flush=True
                )
                times = time_mcp(gateway, op["mcp_tool"], op["mcp_args"], runs)
                s = fmt_stats(times)
                mcp_results[op["name"]] = s
                print(
                    f"| {op['name']} | {s['median']:.0f} | {s['mean']:.0f}"
                    f" | {s['min']:.0f} | {s['max']:.0f} |"
                )
                print(f" {s['median']:.0f} ms", file=sys.stderr)

            gateway.close()
        except Exception as e:
            print(f"\nMCP gateway error: {e}", file=sys.stderr)
            print(
                "Run with --cli-only or fix Docker MCP setup.", file=sys.stderr
            )

    # ---- Schema read overhead ---------------------------------------------
    schema_dir = find_schema_dir()
    if schema_dir:
        print("\n## MCP Schema Read Overhead\n")
        schema_results = time_schema_reads(schema_dir, runs)
        print("| Schema file | Median (ms) | Size (chars) |")
        print("| --- | --- | --- |")
        for fname, data in schema_results.items():
            s = fmt_stats(data["times"])
            print(f"| {fname} | {s['median']:.3f} | {data['size']} |")

    # ---- Side-by-side comparison ------------------------------------------
    if mcp_results:
        print("\n## Comparison (median latency)\n")
        print(
            "| Operation | Atlas CLI (ms) | Docker MCP (ms)"
            " | Difference (ms) | CLI faster by |"
        )
        print("| --- | --- | --- | --- | --- |")
        total_cli = 0
        total_mcp = 0
        for op in OPERATIONS:
            name = op["name"]
            cli_ms = cli_results[name]["median"]
            mcp_ms = mcp_results[name]["median"]
            diff = mcp_ms - cli_ms
            pct = (diff / mcp_ms * 100) if mcp_ms else 0
            total_cli += cli_ms
            total_mcp += mcp_ms
            print(
                f"| {name} | {cli_ms:.0f} | {mcp_ms:.0f}"
                f" | {diff:+.0f} | {pct:.0f}% |"
            )
        diff_total = total_mcp - total_cli
        pct_total = (diff_total / total_mcp * 100) if total_mcp else 0
        print(
            f"| **Total (5 ops)** | **{total_cli:.0f}**"
            f" | **{total_mcp:.0f}** | **{diff_total:+.0f}**"
            f" | **{pct_total:.0f}%** |"
        )


if __name__ == "__main__":
    main()
