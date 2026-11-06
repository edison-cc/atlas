# Atlas CLI Schema Context Benchmarks

Measured on 2026-03-13 from a live Cursor workspace with Docker MCP (MCP_DOCKER) enabled.

## Summary

Enabling an MCP server in Cursor adds context overhead in two ways: **per-turn infrastructure** (MCP wrapper tools, server metadata, usage instructions on every request) and **per-call schema loading** (the model reads each tool's schema before calling it, and the schema stays in conversation history for all subsequent turns). Atlas CLI eliminates both by replacing 73 Atlassian MCP tools with a single 901-char routing rule.

| Cost | Docker MCP | Atlas CLI | Reduction |
|------|-----------|-----------|-----------|
| Per-turn baseline (MCP infrastructure) | ~1,500 tokens | 0 tokens | eliminated |
| Per-call schema read (stays in history) | ~370 tokens/call avg | 0 tokens | eliminated |
| Routing instructions | (in MCP infrastructure) | ~225 tokens | -- |
| Total schema content (73 tools) | 108,867 chars (~27,216 tokens) | 901 chars (~225 tokens) | 121x |

This is a different cost from [BENCHMARKS-OUTPUT.md](BENCHMARKS-OUTPUT.md), which measures per-call output size. Schema costs come from MCP infrastructure, not from the tool results themselves.

## How Cursor loads MCP tools

Cursor does **not** inject all 142 MCP tool schemas as individual tool definitions into every request. Instead, it uses a **lazy-loading** approach:

1. **Per-turn (always present)**: Cursor adds MCP infrastructure to every request -- a generic `CallMcpTool` wrapper tool, MCP server metadata (server names, tool counts), and instructions telling the model how to discover and call MCP tools. This is present on every turn whether or not you use any MCP tools.

2. **Per-call (on demand)**: When the model needs to call a specific MCP tool, it first reads that tool's JSON schema from a descriptor file on disk. The schema enters the conversation as a tool result and **stays in the conversation history for all subsequent turns**.

3. **Accumulating**: Over a multi-turn session, each new MCP tool call adds another schema to the conversation history. By mid-session, multiple schemas may be sitting in history, consuming context on every subsequent turn.

```
[API request to model]
  ├── System instructions
  │     ├── Cursor's own rules
  │     ├── User rules and .mdc rules         ← CLI routing rule lives here
  │     └── MCP usage instructions            ← always present when MCP enabled
  ├── Tool definitions (built-in + MCP wrappers)
  │     ├── Shell, Read, Write, Grep, ...     ← always present
  │     └── CallMcpTool, FetchMcpResource     ← added when MCP enabled
  ├── Open files / codebase context
  └── Conversation history
        ├── User messages + assistant responses
        ├── Tool calls and results
        └── MCP schema reads (accumulate)     ← schemas read on demand, stay here
```

The Docker MCP server exposes **142 tools** totaling **172,064 chars (~43,016 tokens)** of schema content stored as descriptor files. Of those, **73 are Atlassian tools** (49 Jira + 24 Confluence) totaling **108,867 chars (~27,216 tokens)**.

Atlas CLI replaces all of this with a 901-char routing rule in the system instructions. The model already has the Shell tool -- it just needs to know the `atlas` command syntax. No MCP wrapper tools, no schema reads, no accumulating history.

## What gets loaded: MCP vs CLI

### MCP: 73 JSON schemas (108,867 chars on disk)

Each MCP tool has a JSON descriptor file that the model reads before calling that tool. Here is `jira_get_issue` (2,493 chars):

```json
{
  "name": "jira_get_issue",
  "description": "Get details of a specific Jira issue including its Epic links and relationship information.\n\nArgs:\n    ctx: The FastMCP context.\n    issue_key: Jira issue key.\n    fields: Comma-separated list of fields to return (e.g., 'summary,status,customfield_10010'), a single field as a string (e.g., 'duedate'), '*all' for all fields, or omitted for essentials.\n    expand: Optional fields to expand.\n    comment_limit: Maximum number of comments.\n    properties: Issue properties to return.\n    update_history: Whether to update issue view history.\n\nReturns:\n    JSON string representing the Jira issue object.\n\nRaises:\n    ValueError: If the Jira client is not configured or available.",
  "arguments": {
    "type": "object",
    "properties": {
      "comment_limit": {
        "default": 10,
        "description": "Maximum number of comments to include (0 or null for no comments)",
        "maximum": 100,
        "minimum": 0,
        "type": "integer"
      },
      "expand": {
        "default": null,
        "description": "(Optional) Fields to expand. Examples: 'renderedFields' (for rendered content), 'transitions' (for available status transitions), 'changelog' (for history)",
        "type": "string"
      },
      "fields": {
        "default": "assignee,reporter,description,status,created,updated,issuetype,labels,summary,priority",
        "description": "(Optional) Comma-separated list of fields to return ...",
        "type": "string"
      },
      "issue_key": {
        "description": "Jira issue key (e.g., 'PROJ-123', 'PROJ-456')",
        "pattern": "^[A-Z][A-Z0-9_]+-\\d+$",
        "type": "string"
      },
      "properties": { "default": null, "description": "...", "type": "string" },
      "update_history": { "default": true, "description": "...", "type": "boolean" }
    },
    "required": ["issue_key"]
  },
  "outputSchema": { "..." : "..." }
}
```

The model must read this schema before calling `jira_get_issue`, and the schema then stays in conversation history for all subsequent turns. Some schemas are much larger -- `jira_update_proforma_form_answers` is 3,219 chars and contains embedded Python code examples, workaround documentation, and type enumerations.

### CLI: 1 routing rule (901 chars)

Atlas replaces all 73 tool definitions with a Cursor rule (`.mdc` file) that gets included as text in the system instructions:

```
## Atlassian (Jira, Confluence)

Use the `atlas` CLI for all Jira and Confluence operations.

### Jira

- Get issue: `atlas jira get <KEY>` (add `--comments` for comments)
- Search: `atlas jira search "<JQL>" --limit 10`
- Create: `atlas jira create --project PROJ --type Story --summary "..." --parent PROJ-100`
- Update: `atlas jira update <KEY> --summary "..." --description "..."`
- Comment: `atlas jira comment <KEY> "comment text"`
- Transitions: `atlas jira transitions <KEY>` then `atlas jira transition <KEY> <ID>`

### Confluence

- Get page: `atlas conf get <PAGE-ID>`
- Search: `atlas conf search "query" --space SPACE`
- Page tree: `atlas conf tree <SPACE-KEY>`
- Create: `atlas conf create --space SPACE --title "..." --body "..."`
- Update: `atlas conf update <PAGE-ID> --title "..." --body "..."`
- Publish markdown with diagrams: `atlas conf publish <PAGE-ID> input.md --title "..."`
```

901 chars. 12 operations covered. The model already knows how to run shell commands -- it just needs the syntax.

## Per-tool comparison

### Individual tool schema sizes (Jira)

| MCP tool | Schema chars | Equivalent CLI rule line | CLI chars | Reduction |
|----------|-------------|------------------------|-----------|-----------|
| `jira_get_issue` | 2,493 | `atlas jira get <KEY>` | 70 | 36x |
| `jira_search` | 2,730 | `atlas jira search "<JQL>" --limit 10` | 55 | 50x |
| `jira_create_issue` | 2,936 | `atlas jira create --project PROJ ...` | 82 | 36x |
| `jira_update_issue` | 2,358 | `atlas jira update <KEY> ...` | 63 | 37x |
| `jira_add_comment` | 1,656 | `atlas jira comment <KEY> "text"` | 48 | 35x |
| `jira_get_transitions` | 737 | `atlas jira transitions <KEY>` | 66 | 11x |
| `jira_transition_issue` | 1,795 | `atlas jira transition <KEY> <ID>` | 66 | 27x |
| `jira_update_proforma_form_answers` | 3,219 | (not needed) | 0 | -- |
| `jira_get_agile_boards` | 1,506 | (not needed) | 0 | -- |
| `jira_get_sprint_issues` | 1,461 | (not needed) | 0 | -- |
| ... (39 more tools) | ... | (not needed) | 0 | -- |
| **49 Jira tools total** | **70,460** | **6 rule lines** | **384** | **183x** |

### Individual tool schema sizes (Confluence)

| MCP tool | Schema chars | Equivalent CLI rule line | CLI chars | Reduction |
|----------|-------------|------------------------|-----------|-----------|
| `confluence_get_page` | 2,294 | `atlas conf get <PAGE-ID>` | 39 | 59x |
| `confluence_search` | 2,622 | `atlas conf search "query" --space SPACE` | 52 | 50x |
| `confluence_create_page` | 2,820 | `atlas conf create --space SPACE ...` | 66 | 43x |
| `confluence_update_page` | 3,035 | `atlas conf update <PAGE-ID> ...` | 63 | 48x |
| `confluence_get_space_page_tree` | 1,319 | `atlas conf tree <SPACE-KEY>` | 35 | 38x |
| `confluence_upload_attachment` | 2,087 | (not needed) | 0 | -- |
| `confluence_get_page_diff` | 1,210 | (not needed) | 0 | -- |
| ... (17 more tools) | ... | (not needed) | 0 | -- |
| **24 Confluence tools total** | **38,407** | **6 rule lines** | **517** | **74x** |

### Category totals

| Category | MCP tools | MCP chars | MCP tokens | CLI chars | CLI tokens | Reduction |
|----------|----------|-----------|------------|-----------|------------|-----------|
| Jira | 49 | 70,460 | ~17,615 | 384 | ~96 | 183x |
| Confluence | 24 | 38,407 | ~9,601 | 517 | ~129 | 74x |
| **Atlassian total** | **73** | **108,867** | **~27,216** | **901** | **~225** | **121x** |

## Why MCP schemas are so large

The schema bloat comes from several sources:

- **Verbose descriptions**: Each tool includes a full docstring with Args/Returns/Raises sections, often 300-500 chars of prose the model must parse
- **Parameter documentation**: Every parameter has a description, type, default, constraints. `confluence_search` alone embeds 12 CQL query examples (1,000+ chars) in the `query` parameter description
- **Embedded code examples**: `jira_update_proforma_form_answers` contains Python code blocks, workaround documentation, and a full type enumeration (3,219 chars)
- **Niche tools**: 42 of the 73 Atlassian tools cover specialized operations (SLA queries, proforma forms, sprint management, attachment downloads) that most sessions never use. With MCP, the model may still read their schemas when exploring available tools
- **Output schemas**: Every tool includes an `outputSchema` block (~120 chars) that provides no useful information to the model

## Context window impact

### Per-turn baseline cost

Even before any MCP tool is called, enabling the Docker MCP server adds overhead to every turn:

| Component | Tokens (approx) | Present on |
|-----------|-----------------|------------|
| `CallMcpTool` wrapper definition | ~500 | every turn |
| `FetchMcpResource` / `ListMcpResources` definitions | ~300 | every turn |
| MCP server metadata + usage instructions | ~700 | every turn |
| **MCP baseline total** | **~1,500** | **every turn** |
| Atlas CLI routing rule | ~225 | every turn |

With Atlas CLI and MCP disabled, you pay ~225 tokens for the routing rule. With MCP enabled, you pay ~1,500 tokens of infrastructure overhead -- even if you never call a single Atlassian tool.

### Schema accumulation over a session

Because schemas are loaded on demand and stay in conversation history, the context cost grows as you make MCP calls. Each schema read adds ~370 tokens on average (108,867 chars / 73 tools / 4 chars per token) that persist for all subsequent turns.

| Session point | MCP schemas in history | Accumulated schema tokens | Atlas CLI schema tokens |
|--------------|----------------------|--------------------------|------------------------|
| Turn 1 (no calls yet) | 0 | 0 | 0 |
| After 1st MCP call | 1 schema read | ~370 | 0 |
| After 3rd MCP call | 3 schema reads | ~1,110 | 0 |
| After 5th MCP call | 5 schema reads | ~1,850 | 0 |
| After 10th MCP call | 10 schema reads | ~3,700 | 0 |

These schema reads sit in history alongside the MCP baseline overhead (~1,500 tokens/turn). With Atlas CLI, the model runs `atlas` via the Shell tool it already has -- no schema reads, no accumulation.

### Combined impact: infrastructure + schemas + output

Atlas CLI saves context in three independent ways. Using numbers from [BENCHMARKS-OUTPUT.md](BENCHMARKS-OUTPUT.md) for output savings:

| Cost type | When paid | Docker MCP | Atlas CLI | Saved |
|-----------|-----------|-----------|-----------|-------|
| MCP infrastructure | Every turn | ~1,500 tokens | 0 tokens | ~1,500/turn |
| Routing instructions | Every turn | (in MCP infra) | ~225 tokens | -- |
| Schema reads (accumulated) | On demand, stays in history | ~370 tokens/call | 0 tokens | ~370/call |
| Tool output | Each invocation | ~321 tokens/call avg | ~130 tokens/call avg | ~191/call |

Over a 20-turn session with 10 Atlassian calls:

| Metric | Docker MCP | Atlas CLI | Saved |
|--------|-----------|-----------|-------|
| MCP infrastructure (20 turns) | ~30,000 tokens | 0 | ~30,000 |
| Routing rule (20 turns) | 0 | ~4,500 | -- |
| Schema reads in history (10 calls, accumulating) | ~20,350 tokens | 0 | ~20,350 |
| Tool output (10 calls) | ~3,210 tokens | ~1,300 tokens | ~1,910 |
| **Total** | **~53,560 tokens** | **~5,800 tokens** | **~47,760** |

MCP infrastructure dominates -- the ~1,500 tokens of wrapper tools and instructions are paid on every single turn regardless of whether Atlassian tools are used.

## What the model receives on each turn

### With Docker MCP enabled

Cursor adds MCP wrapper tools to the `tools` parameter and MCP metadata to the system instructions on every turn. The model does not see 73 individual Atlassian tools -- instead it sees a generic `CallMcpTool` and is told to read schema files before calling:

```
tools: [
  // Cursor built-in tools
  { "name": "Shell", ... },
  { "name": "Read", ... },
  { "name": "Write", ... },
  ...

  // MCP wrapper tools (always present when any MCP server is enabled)
  { "name": "CallMcpTool", "description": "Call an MCP tool by server identifier...", ... },
  { "name": "FetchMcpResource", ... },
]

system: "...
  You have access to MCP tools through the MCP FileSystem.
  MANDATORY: Always read the tool's schema/descriptor file BEFORE calling
  any tool with CallMcpTool.

  Available MCP servers:
    - MCP_DOCKER (142 tools, 3 prompts enabled)

  Tool descriptors live at:
    ~/.cursor/projects/*/mcps/user-MCP_DOCKER/tools/*.json
..."

conversation_history: [
  // Previous turns may contain schema reads that persist:
  { "role": "tool", "content": "(jira_get_issue.json — 2,493 chars)" },
  { "role": "tool", "content": "(confluence_search.json — 2,622 chars)" },
  // These accumulate with each new MCP tool used
]
```

The model must read a schema file before each new MCP tool call. Once read, the schema stays in conversation history, consuming context on every subsequent turn.

### With Atlas CLI (MCP disabled)

The `tools` parameter contains only Cursor's built-in tools -- no MCP wrapper tools. A 901-char routing rule in the system instructions tells the model how to call `atlas`:

```
tools: [
  // Cursor built-in tools only
  { "name": "Shell", ... },
  { "name": "Read", ... },
  { "name": "Write", ... },
  ...
  // No CallMcpTool, no FetchMcpResource
]

system: "...
  ## Atlassian (Jira, Confluence)

  Use the `atlas` CLI for all Jira and Confluence operations.

  ### Jira
  - Get issue: `atlas jira get <KEY>` (add `--comments` for comments)
  - Search: `atlas jira search "<JQL>" --limit 10`
    ... (4 more lines)

  ### Confluence
  - Get page: `atlas conf get <PAGE-ID>`
    ... (5 more lines)
..."
```

The model calls the Shell tool (already present) to run `atlas` commands. No schema reads, no MCP wrapper tools, no accumulating history.

## How to reproduce

### Measure MCP schema sizes

The MCP tool schemas are stored as JSON descriptor files. In a Cursor workspace with Docker MCP enabled:

```bash
# List Atlassian tool schemas
ls ~/.cursor/projects/*/mcps/user-MCP_DOCKER/tools/jira_*.json \
   ~/.cursor/projects/*/mcps/user-MCP_DOCKER/tools/confluence_*.json

# Count tools and total size
ls jira_*.json confluence_*.json | wc -l        # 73 tools
wc -c jira_*.json confluence_*.json | tail -1   # 108,867 chars total
```

### Measure CLI rule size

```bash
# Extract and measure the Atlassian section of the routing rule
# The routing rule used for this measurement was 1,710 chars including a GitHub section.
# Atlassian section only: 901 chars.
```

## Methodology

- **Chars**: byte length of the JSON descriptor files (MCP) or rule text (CLI)
- **Tokens**: approximate, using 1 token ~ 4 characters (conservative estimate for mixed English/JSON)
- **MCP schemas**: measured from the JSON descriptor files Cursor stores at `~/.cursor/projects/*/mcps/<server>/tools/*.json`. These files contain the tool name, description, and parameter schema. Cursor does not inject all schemas into every request; instead the model reads individual schema files on demand via the `CallMcpTool` workflow. Once read, a schema enters the conversation history and persists for all subsequent turns
- **MCP infrastructure**: the per-turn baseline (~1,500 tokens) is estimated from the `CallMcpTool` / `FetchMcpResource` / `ListMcpResources` tool definitions plus MCP server metadata and usage instructions observed in the system prompt. This overhead is present on every turn when any MCP server is enabled
- **CLI rule**: measured from the Atlassian section of the routing text given to the agent, starting from `## Atlassian` to the end of that section (901 chars). The editor injects that text into the system instructions.
- **Accumulating schema cost**: when the model reads a schema file before calling an MCP tool, the full schema content enters the conversation history as a tool result. This content is included in every subsequent API request for the remainder of the conversation
- **Context window**: tool definitions, system instructions, and conversation history all consume tokens from the same finite context window
