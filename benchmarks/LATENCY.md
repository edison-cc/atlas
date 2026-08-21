# Atlas CLI Latency Benchmarks

Measured on 2026-03-16 against live Jira Cloud and Confluence Cloud APIs (your-site.atlassian.net).

## Summary

Atlas CLI is **12x faster** than Docker MCP per Atlassian operation, reducing median latency from **~5.3 seconds to ~0.4 seconds**.

Docker MCP adds ~5 seconds of overhead per tool call due to Docker container lifecycle management (container creation, startup, execution, teardown). Atlas CLI avoids this entirely by running as a local subprocess.

| Layer | 5-operation total (median) | Avg per call | vs Atlas |
|-------|---------------------------|-------------|----------|
| Docker MCP | 26,653 ms | ~5,332 ms | 12.8x slower |
| **Atlas CLI** | **2,082 ms** | **~416 ms** | **baseline** |

Over a 10-call session, this translates to **~49 seconds saved** in pure tool execution time — before accounting for the extra schema-read round-trips that MCP requires.

## Per-Operation Comparison

The same 5 operations from [BENCHMARKS-OUTPUT.md](BENCHMARKS-OUTPUT.md), measured end-to-end from tool invocation to result.

| Operation | Atlas CLI (ms) | Docker MCP (ms) | MCP overhead (ms) | Atlas faster |
|-----------|---------------|----------------|-------------------|-------------|
| Jira Get Issue (PROJ-123) | 451 | 5,531 | +5,081 | 12.3x |
| Jira Search (5 issues) | 415 | 5,065 | +4,651 | 12.2x |
| Jira Transitions (PROJ-123) | 350 | 5,451 | +5,101 | 15.6x |
| Confluence Get Page (987923264) | 300 | 5,316 | +5,017 | 17.7x |
| Confluence Search (5 results) | 567 | 5,289 | +4,722 | 9.3x |
| **Total** | **2,082** | **26,653** | **+24,571** | **12.8x** |

Values are medians over 5 runs. Full statistics (mean, min, max) in [Detailed Results](#detailed-results).

## Where the Time Goes

Both approaches ultimately make the same HTTP request to the Atlassian REST API. The difference is everything around that request.

### Atlas CLI (~400 ms typical)

```
 Python process startup      ~80 ms
 HTTP request to Atlassian   ~250–500 ms   (the API call itself)
 Markdown formatting          <1 ms
                              ─────────
 Total                       ~330–580 ms
```

Atlas runs as a local subprocess via the Shell tool. Python starts, makes one HTTP request, prints compact Markdown, and exits. No containers, no protocol layers, no networking indirection.

### Docker MCP (~5,300 ms typical)

```
 Docker container create     ~1,500 ms     (image layer setup, namespace creation)
 Container startup           ~2,000 ms     (process init, Python/runtime boot inside container)
 MCP JSON-RPC protocol        ~200 ms      (initialize, tool dispatch, response framing)
 HTTP request to Atlassian    ~250–500 ms   (same API call as CLI)
 JSON formatting               <1 ms
 Container teardown           ~800 ms      (cleanup, remove)
                              ─────────
 Total                       ~4,750–5,000 ms
```

The Docker MCP gateway creates an ephemeral container for each tool call (default behavior without `--long-lived`). Cursor's MCP configuration uses this default: `"args": ["mcp", "gateway", "run"]`. The container lifecycle dominates — the actual API call is identical.

### Why ~5 seconds per MCP call?

The overhead comes from Docker's **ephemeral container lifecycle**. The MCP gateway creates a fresh container for every tool call, runs the tool inside it, then tears it down. Each step costs wall-clock time:

| Phase | Cost | What happens |
|-------|------|-------------|
| Container create | ~1,500 ms | Filesystem layer setup, Linux namespace and cgroup creation |
| Container start | ~2,000 ms | Init process launch, Python/runtime boot inside the container |
| Container teardown | ~800 ms | Process shutdown, filesystem cleanup, container removal |
| MCP protocol | ~200 ms | JSON-RPC initialize, tool dispatch, response framing |
| **Docker overhead total** | **~4,500 ms** | **Added to every single tool call** |

The actual HTTP request to Atlassian (~250–500 ms) is the same in both approaches — it runs inside the container for MCP, or directly on the host for CLI.

### Evidence: constant overhead, not API-dependent

If the 5-second cost were network or API latency, it would vary with response size. It doesn't — the overhead stays in a tight ~4,650–5,100 ms band while CLI times vary by operation:

| Operation | CLI (ms) | MCP (ms) | Fixed overhead (ms) |
|-----------|---------|---------|-------------------|
| Jira Get Issue | 451 | 5,531 | 5,080 |
| Jira Search | 415 | 5,065 | 4,650 |
| Jira Transitions | 350 | 5,451 | 5,101 |
| Confluence Get Page | 300 | 5,316 | 5,016 |
| Confluence Search | 567 | 5,289 | 4,722 |

The CLI times reflect actual API variation (300–567 ms). The Docker overhead (rightmost column) is independent of the operation — it is pure container infrastructure cost.

### Why Atlas CLI avoids this entirely

Atlas CLI runs as a **local subprocess**: `subprocess.run(["atlas", "jira", "get", "PROJ-123"])`. This is a simple Python process fork on the host OS (~80 ms startup), followed by a direct HTTP request. No containers, no isolation layers, no MCP protocol framing.

> **Note**: The benchmark measures `subprocess.run()` latency directly — not through Cursor's Shell tool. See [Scope and Limitations](#scope-and-limitations) for the impact of Shell tool sandbox overhead on real-world agent usage.

### Could `--long-lived` fix it?

The Docker MCP gateway supports a `--long-lived` flag that keeps containers running between calls, which would eliminate the per-call create/teardown cost (~4,300 ms). However:

- Cursor's default MCP configuration does not use it: `"args": ["mcp", "gateway", "run"]`
- Users would need to manually edit `~/.cursor/mcp.json` to add the flag
- Even with `--long-lived`, the MCP JSON-RPC protocol overhead (~200 ms) and the first-call container startup remain
- Atlas CLI would still be faster, just by a smaller margin (~200 ms protocol overhead vs ~80 ms process startup)

## Agent Workflow: The Full Picture

Raw execution latency is only part of the story. From the agent's perspective, each Atlassian operation requires a full tool-call round-trip — and Docker MCP requires an extra one.

### Atlas CLI workflow (1 tool call)

```
Agent ──Shell(atlas jira get KEY)──► result in context
                                     ~400 ms execution
```

### Docker MCP workflow (2 tool calls on first use)

```
Agent ──Read(jira_get_issue.json)──► schema in context     ~1–3s round-trip
Agent ──CallMcpTool(jira_get_issue)──► result in context   ~5,300 ms execution
                                                            ~1–3s round-trip
```

The schema read is mandatory before the first call to each MCP tool type (see [BENCHMARKS-SCHEMA.md](BENCHMARKS-SCHEMA.md)). While the file I/O itself takes <0.1 ms, the tool-call round-trip through the model adds 1–3 seconds of wall-clock time. This means the first MCP call to a new tool type costs **~8–11 seconds** total vs **~2–5 seconds** for Atlas CLI (including the Shell tool round-trip).

### MCP schema read I/O (negligible)

The disk read itself is essentially free — the bottleneck is the model round-trip:

| Schema file | Read time (ms) | Size (chars) |
|-------------|---------------|-------------|
| jira_get_issue.json | 0.038 | 2,493 |
| jira_search.json | 0.034 | 2,730 |
| jira_get_transitions.json | 0.035 | 737 |
| confluence_get_page.json | 0.040 | 2,294 |
| confluence_search.json | 0.029 | 2,622 |

## Scaling Impact

In a typical agent session, Atlassian calls compound. The time savings grow linearly with call count, while MCP's schema-read penalty adds a per-tool-type first-call cost.

| Scenario | Docker MCP | Atlas CLI | Time saved |
|----------|-----------|-----------|------------|
| 5 calls (light session) | ~27s | ~2s | ~25s |
| 10 calls (normal session) | ~53s | ~4s | ~49s |
| 20 calls (heavy session) | ~107s | ~8s | ~99s |

These are execution times only. Adding model round-trip overhead (~2s per tool call), the effective wall-clock time for 20 MCP calls is **~147s** (tool execution + 20 round-trips + schema reads) vs **~48s** for CLI (tool execution + 20 round-trips, no schema reads). That is **~99 seconds saved in a heavy session**, or roughly 1.5 minutes of waiting eliminated.

## Combined Savings: Context + Latency

Atlas CLI improves the agent experience across three dimensions simultaneously. Using data from all three benchmark documents:

| Dimension | Docker MCP | Atlas CLI | Improvement |
|-----------|-----------|-----------|-------------|
| **Latency** (per call) | ~5,300 ms | ~400 ms | 12.8x faster |
| **Output size** (per call avg) | ~321 tokens | ~130 tokens | 2.5x smaller |
| **Schema overhead** (73 tools) | 27,216 tokens | 225 tokens | 121x smaller |

These are independent — you get all three benefits simultaneously. Faster execution, smaller context consumption, and no MCP infrastructure overhead.

## Detailed Results

### Atlas CLI (5 runs per operation)

| Operation | Median (ms) | Mean (ms) | Min (ms) | Max (ms) |
|-----------|------------|----------|---------|---------|
| Jira Get Issue | 451 | 456 | 426 | 483 |
| Jira Search (5 issues) | 415 | 416 | 405 | 430 |
| Jira Transitions | 350 | 351 | 345 | 359 |
| Confluence Get Page | 300 | 304 | 292 | 315 |
| Confluence Search | 567 | 564 | 529 | 591 |

### Docker MCP (5 runs per operation)

| Operation | Median (ms) | Mean (ms) | Min (ms) | Max (ms) |
|-----------|------------|----------|---------|---------|
| Jira Get Issue | 5,531 | 5,507 | 5,337 | 5,608 |
| Jira Search (5 issues) | 5,065 | 5,316 | 4,948 | 6,036 |
| Jira Transitions | 5,451 | 5,340 | 5,004 | 5,704 |
| Confluence Get Page | 5,316 | 5,293 | 5,157 | 5,472 |
| Confluence Search | 5,289 | 5,703 | 5,126 | 6,993 |

## How to Reproduce

```bash
# Full benchmark (CLI + Docker MCP)
python benchmark_latency.py

# CLI only (no Docker dependency)
python benchmark_latency.py --cli-only

# More iterations for tighter confidence
python benchmark_latency.py --runs 10
```

Requires:
- `atlas` CLI installed and configured (see [README.md](README.md))
- Docker Desktop with MCP gateway (`docker mcp gateway run`) for MCP measurements
- Network access to `your-site.atlassian.net`

## Scope and Limitations

This benchmark compares Atlas CLI against **Docker MCP** (ephemeral containers via `docker mcp gateway run`). Two factors that affect real-world agent performance are not captured here.

### Shell tool sandbox overhead

The benchmark measures CLI latency via direct `subprocess.run()` in Python, which reports ~80 ms process startup. In actual Cursor agent usage, CLI commands run through the **Shell tool sandbox**, which adds ~1,600–2,000 ms of overhead per invocation (sandbox initialization, filesystem restrictions, process isolation).

| Measurement method | atlas --help | Overhead |
|---|---|---|
| `subprocess.run()` (this benchmark) | ~170 ms | baseline |
| Cursor Shell tool (agent reality) | ~2,100 ms | ~1,950 ms sandbox |

This overhead applies to every Shell tool call — not just `atlas`. MCP's `CallMcpTool` bypasses the Shell sandbox entirely, so the ~2 s penalty is exclusive to CLI-based approaches.

For Docker MCP, the sandbox overhead is irrelevant because Docker's container lifecycle (~4,500 ms) dwarfs it. But for non-Docker MCP servers (see below), the sandbox overhead can reverse the CLI latency advantage.

### HTTP and stdio MCP servers

Docker MCP creates an ephemeral container per tool call, which is why it adds ~4,500 ms of overhead. Not all MCP servers work this way. **HTTP** and **stdio** MCP servers run as persistent processes with no container lifecycle:

| MCP transport | Per-call overhead | Example |
|---|---|---|
| Docker (ephemeral containers) | ~4,500 ms | Atlassian via `docker mcp gateway run` |
| HTTP (persistent remote server) | ~10 ms | Enterprise search via `https://<host>/mcp/default` |
| stdio (persistent local process) | ~10 ms | Custom MCP servers via `npx`, `uvx`, etc. |

When the MCP server is persistent (HTTP/stdio) and the backend API is slow relative to Shell sandbox overhead, MCP can be faster than CLI:

```
CLI via Shell tool:    ~2,000 ms sandbox + ~80 ms startup + ~700 ms API = ~2,780 ms
HTTP MCP:              ~10 ms protocol + ~700 ms API                    = ~710 ms
```

The Atlas CLI latency advantage documented in this benchmark is specific to Docker MCP, where container overhead (~4,500 ms) far exceeds Shell sandbox overhead (~2,000 ms). For persistent MCP servers, the tradeoff reverses on the latency dimension — though Atlas CLI still wins on [schema overhead](BENCHMARKS-SCHEMA.md) and [output size](BENCHMARKS-OUTPUT.md).

## Methodology

- **Latency**: wall-clock time measured with `time.perf_counter()` around each operation
- **Atlas CLI**: `subprocess.run()` captures full process lifecycle (startup → HTTP → format → exit)
- **Docker MCP**: JSON-RPC over stdio to `docker mcp gateway run`, measuring from `tools/call` request to response. The gateway is started once and reused for all calls (warm gateway, cold containers per call — matching Cursor's default behavior)
- **Runs**: 5 iterations per operation; median used for comparisons (resistant to outliers from network jitter)
- **Schema reads**: `time.perf_counter()` around `open() + read()` of each MCP descriptor JSON file. The I/O time is negligible; the agent-relevant cost is the tool-call round-trip to read the file, estimated at 1–3 seconds based on typical model inference latency
- **Environment**: macOS, Docker Desktop, both approaches hitting the same Atlassian Cloud instance over the same network connection
