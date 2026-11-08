# Schema size and agent context

## Historical observation: March 2026

A previous Cursor/Docker MCP workspace reportedly contained 73 Atlassian schema
files totaling 108,867 bytes. A historical routing rule was 901 bytes including its
trailing newline and described 12 operations. Their ratio is 120.83.

This is **not a measurement of actual agent context savings**. The two collections
do not cover equivalent functionality; the original schemas and exact environment
are unavailable. The current routing instruction also differs from that historical
rule. The former “121x less context” headline is withdrawn.

The previous ~1,500 tokens/turn infrastructure estimate and ~47,000 cumulative-token
saving projection were not tokenizer-based session measurements. Tool discovery,
repeated calls, CLI help, other enabled servers, caching and compaction all affect
actual input. Cumulative input across requests is different from peak context.

## Replacement methodology

See [the benchmark protocol](README.md#agent-context). Compare shared tasks in a
fixed agent/model version and retain request-level evidence. Include instructions,
help/schema discovery, invocation arguments, result bodies and tool envelopes.
Measure actual tokens with a named tokenizer or provider accounting. Report peak
context separately from cumulative input and cached tokens.

Without those records, no current numerical context reduction is claimed.
See also [output size](OUTPUT.md) and [execution latency](LATENCY.md).
