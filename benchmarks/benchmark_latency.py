#!/usr/bin/env python3
"""Validated, interleaved CLI/Docker MCP timing. See benchmarks/README.md."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import platform
from pathlib import Path
import queue
import statistics
import subprocess
import sys
import threading
import time


class McpGateway:
    """Communicates with `docker mcp gateway run` over stdio."""

    def __init__(self, command, timeout=60):
        self._msg_id = 0
        self._responses: queue.Queue = queue.Queue()
        self._timeout = timeout

        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

        try:
            self.request("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "atlas-benchmark", "version": "2"},
            })
            self._notify("notifications/initialized", {})
        except Exception:
            self.close()
            raise

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
                        if not hdr or hdr.strip() == b"":
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
                if "error" in resp:
                    raise RuntimeError(f"MCP {method} returned a JSON-RPC error")
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
            self.proc.wait(timeout=5)


def validate_text(text, expected):
    if not text.strip() or any(value not in text for value in expected):
        raise ValueError("Empty output or missing expected content; sample rejected")


def run_cli(command, expected):
    start = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=60)
    elapsed = (time.perf_counter() - start) * 1000
    if result.returncode:
        raise RuntimeError(f"CLI exited with status {result.returncode}; sample rejected")
    validate_text(result.stdout, expected)
    return elapsed, result.stdout


def run_mcp(gateway, name, arguments, expected):
    start = time.perf_counter()
    response = gateway.call_tool(name, arguments)
    elapsed = (time.perf_counter() - start) * 1000
    if "error" in response or not isinstance(response.get("result"), dict):
        raise RuntimeError("MCP returned an error or missing result; sample rejected")
    result = response["result"]
    if result.get("isError"):
        raise RuntimeError("MCP tool returned isError; sample rejected")
    text = "\n".join(item.get("text", "") for item in result.get("content", [])
                     if item.get("type") == "text")
    if not text and "structuredContent" in result:
        text = json.dumps(result["structuredContent"], ensure_ascii=False)
    validate_text(text, expected)
    return elapsed, text


def fmt_stats(times):
    return {"n": len(times), "median_ms": statistics.median(times),
            "p95_ms": sorted(times)[math.ceil(len(times) * .95) - 1],
            "min_ms": min(times), "max_ms": max(times)}


def load_cases(path):
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Cases must be a nonempty JSON list")
    names = set()
    for case in cases:
        name = case.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Case names must be nonempty and unique")
        names.add(name)
        for key in ("cli", "expect_cli", "expect_mcp"):
            if not isinstance(case.get(key), list) or not case[key] or not all(
                isinstance(value, str) and value.strip() for value in case[key]
            ):
                raise ValueError(f"{name}: {key} must contain nonempty strings")
        if not isinstance(case.get("mcp_tool"), str) or not case["mcp_tool"] or not isinstance(case.get("mcp_args"), dict):
            raise ValueError(f"{name}: specify mcp_tool and mcp_args")
    return cases


def command_version(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        return result.stdout.strip() if result.returncode == 0 else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="Reviewed JSON cases; see cases.example.json")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--cli-only", action="store_true")
    parser.add_argument("--server", help="Docker MCP server identifier")
    parser.add_argument("--server-version", help="Server version or image digest for provenance")
    parser.add_argument("--mode", choices=["ephemeral", "persistent"], default="ephemeral")
    parser.add_argument("--atlas", default="atlas", help="Atlas executable")
    parser.add_argument("--output", required=True, help="New JSON result file (will not overwrite)")
    args = parser.parse_args()
    if args.runs < 1 or args.warmup < 0:
        parser.error("runs must be positive; warmup must be nonnegative")
    if not args.cli_only and (not args.server or not args.server_version):
        parser.error("MCP comparison requires --server and --server-version")
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    command = ["docker", "mcp", "gateway", "run", "--servers", args.server or ""]
    if args.mode == "persistent":
        command.append("--long-lived")
    report = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
              "environment": {"platform": platform.platform(), "python": platform.python_version(),
                              "atlas": command_version([args.atlas, "--version"]),
                              "docker": command_version(["docker", "--version"]) if not args.cli_only else None,
                              "server_version": args.server_version,
                              "gateway_command": command if not args.cli_only else None},
              "runs": args.runs, "warmup": args.warmup, "cases": cases,
              "samples": [], "summary": []}
    gateway = None
    # Reserve output before starting any requests; failed runs preserve partial samples.
    with open(args.output, "x", encoding="utf-8") as output:
        try:
            if not args.cli_only:
                gateway = McpGateway(command)
            for case in cases:
                print(f"Measuring {case['name']}...", file=sys.stderr, flush=True)
                methods = ["cli"] if args.cli_only else ["cli", "mcp"]
                for index in range(args.warmup + args.runs):
                    phase = "warmup" if index < args.warmup else "measured"
                    for method in methods[::1 if index % 2 == 0 else -1]:
                        if method == "cli":
                            elapsed, text = run_cli([args.atlas, *case["cli"]], case["expect_cli"])
                        else:
                            elapsed, text = run_mcp(gateway, case["mcp_tool"], case["mcp_args"], case["expect_mcp"])
                        report["samples"].append({"case": case["name"], "method": method,
                            "phase": phase, "iteration": index, "elapsed_ms": elapsed,
                            "chars": len(text), "utf8_bytes": len(text.encode("utf-8")),
                            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
            for case in cases:
                for method in methods:
                    times = [s["elapsed_ms"] for s in report["samples"] if s["case"] == case["name"]
                             and s["method"] == method and s["phase"] == "measured"]
                    report["summary"].append({"case": case["name"], "method": method, **fmt_stats(times)})
            report["status"] = "complete"
        except Exception as exc:
            report["status"] = "failed"
            # Avoid persisting API response bodies or subprocess output containing private data.
            report["failure_type"] = type(exc).__name__
            report["failed_case"] = case["name"] if "case" in locals() else None
            report["failed_method"] = method if "method" in locals() else "gateway"
            print(f"Benchmark failed ({type(exc).__name__}); no valid comparison produced.", file=sys.stderr)
        finally:
            if gateway:
                gateway.close()
            json.dump(report, output, indent=2, ensure_ascii=False)
            output.write("\n")
    if report["status"] != "complete":
        return 1
    print("| Operation | Method | N | Median ms | p95 ms |")
    print("| --- | --- | --- | --- | --- |")
    for row in report["summary"]:
        print(f"| {row['case']} | {row['method']} | {row['n']} | {row['median_ms']:.1f} | {row['p95_ms']:.1f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
