# How MCP Works and Why It Bloats Context

MCP (Model Context Protocol) connects external tool servers to LLMs in agent workflows. This document explains how MCP tools are loaded into context, how different IDEs have evolved their loading strategies, and when CLI-based alternatives win.

## How MCP works in agent IDEs

An MCP server exposes tools (functions the model can call) over a transport layer. The agent IDE connects to the server, discovers its tools, and makes them available to the LLM. The flow:

```
User → IDE → LLM → tool call → MCP server → external API (Jira, enterprise search, etc.)
```

The LLM needs to know what tools exist and what arguments they accept. This information -- tool names, descriptions, parameter schemas -- must be present in the LLM's context window for the model to use the tools. How much schema information gets loaded, and when, is where IDEs diverge.

## The context bloat problem

Every MCP tool has a JSON schema describing its name, description, parameters, types, defaults, and constraints. A typical tool schema is 1,000-3,000 chars (~250-750 tokens). This adds up fast:

| Scale | Tools | Schema tokens (approx) |
|---|---|---|
| Small MCP server (enterprise search) | 3 | ~750 |
| Medium MCP server | 20-30 | 3,000-6,000 |
| Large MCP server (Atlassian Docker MCP) | 73 | ~27,000 |
| Multiple servers (GitHub + Atlassian + others) | 100+ | 20,000-150,000 |

One audit of 11 popular MCP servers found 22,945 tokens injected before a single user message. An extreme case burned 143,000 of a 200,000-token context window on tool definitions alone.

The cost compounds because tool definitions (or schema reads) are present on every turn of a multi-turn conversation, consuming tokens that could otherwise hold code, files, or reasoning.

## How each IDE loads MCP tools

IDEs have taken three distinct approaches, evolving from naive to sophisticated.

### Approach 1: Inject all schemas (early VS Code, pre-late 2025)

The simplest approach: register every MCP tool as an individual tool definition in every LLM API request.

```
Every LLM request includes:
  tools: [
    { name: "jira_get_issue", parameters: { ... 2,493 chars ... } },
    { name: "jira_search", parameters: { ... 2,730 chars ... } },
    { name: "jira_create_issue", parameters: { ... 2,936 chars ... } },
    ... (70 more Atlassian tools)
    ... (tools from every other enabled MCP server)
  ]
```

**Cost**: All schemas on every turn. 73 Atlassian tools = ~27,000 tokens on every request, whether or not you call any of them.

**Problem**: Doesn't scale. Users with multiple MCP servers quickly exhaust context windows before doing any actual work.

### Approach 2: Wrapper + on-demand file reads (Cursor, current)

Cursor uses a lazy-loading approach with a generic wrapper tool called `CallMcpTool`:

1. **Per-turn (always present)**: Cursor injects `CallMcpTool`, `FetchMcpResource`, MCP server metadata, and usage instructions (~1,500 tokens total). This is present on every turn when any MCP server is enabled.

2. **Per-call (on demand)**: When the model wants to call a specific MCP tool, it first reads that tool's JSON schema from a descriptor file on disk. The schema enters the conversation as a tool result.

3. **Accumulating**: Once a schema is read, it stays in conversation history for all subsequent turns. Each new MCP tool type adds ~370 tokens (average) that persist.

```
Turn 1:  [1,500 tokens MCP infrastructure]
Turn 5:  [1,500 infra] + [schema A read: 623 tokens in history]
Turn 8:  [1,500 infra] + [schema A: 623] + [schema B: 370] + [schema C: 685]
Turn 20: [1,500 infra] + [all previously read schemas still in history]
```

**Cost**: ~1,500 tokens/turn baseline + ~370 tokens per unique tool used (accumulates). Over a 20-turn session with 10 Atlassian calls: ~50,000+ tokens.

**Improvement over Approach 1**: Schemas for unused tools are never loaded. But schemas for used tools accumulate permanently in conversation history.

### Approach 3: Tool Search with proxy tools (VS Code 2026, Claude Code)

The most aggressive approach: replace all MCP tool definitions with a small set of proxy tools.

**VS Code (Jan 2026+)** implements "MCP Tool Search":
- Only tool names and short descriptions are loaded initially
- Full `input_schema` is fetched just-in-time when the model's intent matches a tool description
- Automatically activates when tool descriptions would consume more than 10% of context

**Claude Code (v2.1.7+)** uses 4 proxy tools:
- `search_tools` -- find relevant tools by description
- `get_tool_schema` -- fetch full schema for a specific tool
- `call_tool` -- execute the tool
- `list_servers` -- list available MCP servers

```
Every LLM request includes:
  tools: [
    { name: "search_tools", ... },    // ~150 tokens
    { name: "get_tool_schema", ... }, // ~150 tokens
    { name: "call_tool", ... },       // ~150 tokens
    { name: "list_servers", ... },    // ~150 tokens
  ]
  // Total: ~600 tokens constant, regardless of how many MCP tools exist
```

**Cost**: ~600 tokens constant. Full schemas fetched only at call time, potentially not persisted in history the same way.

**Improvement**: 85-96% token reduction compared to injecting all schemas. A setup with 50 tools (~10,000 tokens/turn) drops to ~600 tokens constant.

### Comparison

| IDE | Approach | 73-tool schema cost | Accumulates? |
|---|---|---|---|
| Early VS Code | Inject all | ~27,000 tokens/turn | No (same cost every turn) |
| Cursor | Wrapper + file reads | ~1,500/turn + ~370/call in history | Yes (schemas stay in history) |
| VS Code (2026) | Tool Search | Names + descriptions only until needed | Minimal |
| Claude Code | 4 proxy tools | ~600 tokens constant | Minimal |

## Why CLIs avoid this entirely

A CLI like `atlas` sidesteps the entire MCP schema loading problem by using the Shell tool that every IDE already provides. The model doesn't need to discover tools or read schemas -- it just needs a routing rule telling it the command syntax:

```
## Atlassian (Jira, Confluence)
Use the `atlas` CLI for all Jira and Confluence operations.
- Get issue: `atlas jira get <KEY>`
- Search: `atlas jira search "<JQL>" --limit 10`
...
```

This routing rule is 901 chars (~225 tokens), loaded once in the system instructions. It replaces 73 tool schemas (108,867 chars, ~27,000 tokens) with no accumulation, no infrastructure overhead, no schema reads.

| Dimension | MCP (any approach) | CLI routing rule |
|---|---|---|
| Infrastructure overhead | 600-1,500 tokens/turn | 0 |
| Schema loading | 370-27,000 tokens | 0 |
| Routing instructions | 0 | ~225 tokens/turn |
| Accumulation in history | Varies by IDE | None |

## When MCP still wins

The CLI advantage is not universal. MCP is the better choice when:

- **The MCP server has few tools** (e.g., an enterprise-search server with 3 tools) -- schema overhead is trivial
- **The server uses HTTP/stdio transport** (persistent process, no container overhead) -- no per-call latency penalty
- **The backend API is slow** relative to Shell tool sandbox overhead (~1.6-2 s in Cursor) -- MCP's `CallMcpTool` bypasses the sandbox
- **You're already paying MCP infrastructure costs** for another server -- adding a small server is marginal

The CLI advantage is strongest when:

- **The MCP server has many tools** (73 Atlassian tools) -- massive schema bloat
- **The server uses Docker containers** (ephemeral, ~4.5 s overhead per call)
- **Output is verbose** (nested JSON vs compact Markdown)
- **You can disable MCP entirely** -- eliminating the per-turn infrastructure cost

## References

- [BENCHMARKS-SCHEMA.md](../benchmarks/SCHEMA.md) -- Measured schema overhead for Atlassian Docker MCP vs Atlas CLI
- [BENCHMARKS-LATENCY.md](../benchmarks/LATENCY.md) -- Latency comparison including Shell sandbox overhead analysis
- [BENCHMARKS-OUTPUT.md](../benchmarks/OUTPUT.md) -- Per-call output size comparison
- [VS Code MCP Tool Search issue](https://github.com/microsoft/vscode/issues/288310)
- [MCP context window problem analysis](https://www.junia.ai/blog/mcp-context-window-problem)
- [MCP tool schema audit (11 servers, 22,945 tokens)](https://dev.to/0coceo/i-audited-11-mcp-servers-22945-tokens-before-a-single-message-31e)
