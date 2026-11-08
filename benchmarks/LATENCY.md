# Execution latency

## Historical observations: March 2026

The following medians were reported for five runs per operation against one
Atlassian Cloud site through Atlas subprocesses and a warm Docker MCP gateway
using ephemeral containers. Original raw samples and complete version/configuration
records are unavailable. The original script accepted unsuccessful responses;
therefore these numbers have not been independently validated and are **not
verified current-release performance claims**.

| Operation | Atlas CLI ms | Docker MCP ms |
|---|---:|---:|
| Jira Get Issue | 451 | 5,531 |
| Jira Search | 415 | 5,065 |
| Jira Transitions | 350 | 5,451 |
| Confluence Get Page | 300 | 5,316 |
| Confluence Search | 567 | 5,289 |
| Sum of displayed medians | 2,083 | 26,652 |

The original totals were 2,082 and 26,653 ms, a 12.8x ratio. The discrepancy may
reflect rounding but cannot be resolved without raw samples. Dividing a sum of
per-operation medians by five yields an average of medians, not a pooled per-call
median. Session time-saving projections based on those values are not retained.

## New measurements

Use [the validated benchmark protocol](README.md#latency) and
[benchmark_latency.py](benchmark_latency.py). No replacement live results have
been recorded yet. Example commands now run from the repository root and require
explicit cases, server identity/version, and a new output file.

Report per-operation median/p95, all raw samples, versions and failure counts.
Compare ephemeral and persistent configurations independently. Docker exposes
[`--long-lived` and `--static`](https://docs.docker.com/reference/cli/docker/mcp/gateway/run/);
configuration affects the result. A single Docker setup cannot establish a speed
advantage over MCP generally. No fixed protocol overhead or persistent-server
speed advantage is claimed without direct measurements.

The runner times subprocess execution and gateway `tools/call` requests. It excludes
gateway startup, agent/model scheduling and shell sandbox overhead. Actual coding
agent latency requires separate end-to-end measurements. See [schema/context
methodology](SCHEMA.md) and [historical output observations](OUTPUT.md).
