# atlas

Faster Jira and Confluence for AI coding agents.

- **121x less context** -- one routing rule replaces 73 MCP tool schemas
- **60% smaller output** -- flat Markdown, not nested JSON
- **12x faster** -- direct HTTP in ~400 ms vs ~5,300 ms per Docker MCP call

## Why atlas?

In agent workflows (Cursor, Copilot, etc.), Docker-based MCP servers impose hidden costs: tool schemas that bloat context, verbose JSON output, and container overhead on every call. Atlas CLI eliminates all three. Measurements below were taken against live Atlassian Cloud APIs.

| Dimension | Docker MCP | Atlas CLI | Improvement | Details |
|-----------|-----------|-----------|-------------|---------|
| Schema overhead (73 tools) | 108,867 chars (~27,216 tokens) | 901 chars (~225 tokens) | **121x smaller** | [benchmarks/SCHEMA.md](benchmarks/SCHEMA.md) |
| Output size (5-op total) | 6,421 chars (~1,605 tokens) | 2,597 chars (~649 tokens) | **60% smaller** | [benchmarks/OUTPUT.md](benchmarks/OUTPUT.md) |
| Latency (per call median) | ~5,300 ms | ~400 ms | **12.8x faster** | [benchmarks/LATENCY.md](benchmarks/LATENCY.md) |

> **Scope**: These benchmarks compare Atlas CLI against **Docker MCP** (ephemeral containers). Not all MCP servers use Docker — HTTP and stdio MCP servers run as persistent processes with negligible per-call overhead. For persistent MCP servers, the latency tradeoff can reverse because Cursor's Shell tool sandbox adds ~1.6–2 s per CLI invocation that `CallMcpTool` avoids. Atlas CLI still wins on schema overhead and output size regardless of MCP transport. See [benchmarks/LATENCY.md — Scope and Limitations](benchmarks/LATENCY.md#scope-and-limitations) for details.

### See the difference

The same issue fetched through Docker MCP vs Atlas CLI — full comparison with raw API output (27,788 chars for the same issue) in [benchmarks/OUTPUT.md](benchmarks/OUTPUT.md).

### Schema overhead -- 121x reduction

Enabling Docker MCP injects ~1,500 tokens of infrastructure (wrapper tools, server metadata, usage instructions) into **every turn**, whether or not you call an Atlassian tool. On top of that, each new MCP tool call triggers a schema read (~370 tokens on average) that **stays in conversation history** for all subsequent turns.

Atlas CLI replaces 73 Atlassian tool schemas (108,867 chars) with a single 901-char routing rule -- a **121x reduction**. Over a 20-turn session with 10 Atlassian calls, this saves ~47,000 tokens of context. Details in [benchmarks/SCHEMA.md](benchmarks/SCHEMA.md).

### Output size -- 60% fewer tokens

Docker MCP returns nested JSON containing avatar URLs, null custom fields, status metadata, and ADF document trees. Atlas emits flat Markdown with only the fields the model needs.

Across 5 representative operations, Atlas produces **2,597 chars (~649 tokens)** vs Docker MCP's **6,421 chars (~1,605 tokens)** -- a **60% reduction**. Compared to the raw Atlassian API (41,567 chars), the savings reach **96%**. Details in [benchmarks/OUTPUT.md](benchmarks/OUTPUT.md).

### Execution latency -- 12x faster

Docker MCP creates an ephemeral container for every tool call, adding ~4,500 ms of container lifecycle overhead (create, start, teardown). Atlas runs as a local subprocess that starts in ~80 ms and makes a direct HTTP request.

Median per-call latency drops from **~5,300 ms to ~400 ms** -- a **12.8x speedup**. Over a 10-call session, that is **~49 seconds saved** in pure execution time. Details in [benchmarks/LATENCY.md](benchmarks/LATENCY.md).

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — install with:
  - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: install [Git for Windows](https://gitforwindows.org/) (includes Git Bash), then run the macOS/Linux command above inside Git Bash
- An [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens)

### 1. Install

```bash
uv tool install git+https://github.com/edison-cc/atlas.git
```

> **Windows:** Close and reopen your terminal after installing `uv` and again after `uv tool install` for `PATH` changes to take effect.

Or install from source:

```bash
git clone https://github.com/edison-cc/atlas.git
cd atlas
uv pip install .
```

> **No uv?** You can also use `pip install .` in a virtual environment.

Verify: `atlas --help`

### 2. Configure Atlassian credentials

Create `~/.config/atlas/config.json`:

```json
{
  "atlassian_email": "you@example.com",
  "atlassian_api_token": "your-api-token",
  "atlassian_base_url": "https://your-site.atlassian.net/"
}
```

Generate a token at https://id.atlassian.com/manage-profile/security/api-tokens

> **Tip:** You can use environment variables instead of a config file: `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`, `ATLASSIAN_BASE_URL`.
>
> **Story points not showing?** Your Jira instance may use a non-standard field ID. Run `atlas jira fields --search "story"` to find it, then add `"story_points_field": "customfield_XXXXX"` to your config.

### Upgrade

```bash
uv tool upgrade atlas-cli
```

<details>
<summary><strong>Windows notes</strong></summary>

We recommend **Git Bash** (included with [Git for Windows](https://gitforwindows.org/)). All commands in this guide work identically in Git Bash — no Windows-specific steps needed.

After installing `uv` and `atlas`, close and reopen Git Bash for `PATH` changes to take effect.

**No Git Bash?** If you are using PowerShell, download [config.json.example](https://raw.githubusercontent.com/edison-cc/atlas/main/config.json.example) as a config template and fill in your values, and use `Invoke-WebRequest` in place of `curl`.

</details>

## Editor setup

Atlas CLI is designed to be called by an AI coding agent via the shell tool. The agent needs a rule or instruction file that routes Atlassian operations through `atlas` instead of MCP. Choose the section that matches your editor.

### VS Code Copilot

Copilot's agent mode can call `atlas` through the terminal. This repo ships a ready-to-use instruction file at [`.github/copilot-instructions.md`](.github/copilot-instructions.md) that Copilot loads automatically when you open this repo.

#### Per-project instructions (for shared projects)

To add atlas routing to another project, copy the instruction file:

```bash
mkdir -p .github
curl -fsSL https://raw.githubusercontent.com/edison-cc/atlas/main/.github/copilot-instructions.md \
  -o .github/copilot-instructions.md
```

Commit `.github/copilot-instructions.md` to the repo so all contributors have it.

#### Global user instructions (all workspaces)

To make Copilot aware of `atlas` in every workspace, add the following to your VS Code **User** `settings.json` (open with `Cmd+Shift+P` → "Preferences: Open User Settings (JSON)"):

```json
{
  "github.copilot.chat.codeGeneration.instructions": [
    {
      "text": "Use the `atlas` CLI for all Jira and Confluence operations. Run `atlas jira --help` or `atlas conf --help` to discover commands and flags."
    }
  ]
}
```

### Cursor

Cursor's agent doesn't know about `atlas` by default. The recommended path depends on your situation:

- **Individual use** → install the Cursor skill. It auto-discovers new flags via `--help` and works across all workspaces.
- **Shared project** → commit a per-project rule so all contributors get it automatically.

#### Skill install (individual use)

```bash
mkdir -p ~/.cursor/skills/atlas-cli
curl -fsSL https://raw.githubusercontent.com/edison-cc/atlas/main/.cursor/skills/atlas-cli/SKILL.md \
  -o ~/.cursor/skills/atlas-cli/SKILL.md
```

#### Per-project rule (for shared projects)

This repo ships a ready-to-use rule at [`.cursor/rules/dev-tools.mdc`](.cursor/rules/dev-tools.mdc). In your target project, run:

```bash
mkdir -p .cursor/rules
curl -fsSL https://raw.githubusercontent.com/edison-cc/atlas/main/.cursor/rules/dev-tools.mdc \
  -o .cursor/rules/dev-tools.mdc
```

Commit `.cursor/rules/dev-tools.mdc` to the repo so all contributors have it. To update after a new release, re-run the `curl` command above.

#### Global user rule

If you prefer not to install the skill file, paste the following into **Cursor Settings > Rules > User Rules**:

```
Use the `atlas` CLI for all Jira and Confluence operations.

- Get issue: atlas jira get <KEY>
- Search:    atlas jira search "<JQL>" --limit 10 --story-points --parent
- Children:  atlas jira children <KEY> --story-points --depth 2
- Parent:    atlas jira parent <KEY> --depth 5
- Fields:    atlas jira fields --search "story"
- Create:    atlas jira create --project PROJ --type Story --summary "..." --parent PROJ-100 --ac "..."
- Update:    atlas jira update <KEY> --summary "..." --description "..." --ac "..."
- Comment:   atlas jira comment <KEY> "comment text"
- Transitions: atlas jira transitions <KEY> then atlas jira transition <KEY> <ID>
- Discover flags: atlas jira create --help, atlas jira update --help
- Get page:  atlas conf get <PAGE-ID>
- Search:    atlas conf search "query" --space SPACE
- Page tree: atlas conf tree <SPACE-KEY>
- Create:    atlas conf create --space SPACE --title "..." --body "..."
- Update:    atlas conf update <PAGE-ID> --title "..." --body "..."
- Publish:   atlas conf publish <PAGE-ID> input.md --title "..."
```

To update after a new release, copy the latest snippet from this README and re-paste it into User Rules.

## CLI reference

Atlas also works as a standalone terminal CLI without any editor integration.

### Jira

```bash
atlas jira get PROJ-123  # issue details
atlas jira get PROJ-123 --comments  # with comments
atlas jira search "project = PROJ AND status = Open"  # JQL search
atlas jira search "parent = PROJ-100" --story-points --parent  # extra columns
atlas jira children PROJ-100 --story-points  # recursive
atlas jira children PROJ-100 --depth 3 --limit 200  # deeper traversal
atlas jira parent PROJ-123  # ancestor chain
atlas jira fields --search "story"  # discover field IDs
atlas jira create --project PROJ --type Story --summary "Add feature X" --parent PROJ-100 --ac "- criterion 1"
atlas jira update PROJ-123 --summary "New title" --ac "- updated criterion"
atlas jira comment PROJ-123 "This is a comment"
atlas jira transitions PROJ-123  # list available
atlas jira transition PROJ-123 31  # move to status
atlas jira create --help  # discover all flags
```

### Confluence

```bash
atlas conf get 12345678  # page content
atlas conf search "architecture" --space DEV  # search
atlas conf tree DEV  # page hierarchy
atlas conf create --space DEV --title "New Page" --body "content"
atlas conf update 12345678 --title "Updated" --body "new content"
atlas conf publish 12345678 doc.md --title "Design Doc"  # publish with Mermaid
atlas conf --help  # list commands
```

## Adding commands

Each command is a single file in `atlas/commands/`. Create a new file with `register(subparser)` and `run(args, client)` functions — it's auto-discovered.
