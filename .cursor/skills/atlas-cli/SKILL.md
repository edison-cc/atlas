---
name: atlas-cli
description: >-
  Use the atlas CLI for Jira and Confluence operations. Use when the user
  mentions Jira issues, Confluence pages, Atlassian, or asks to create,
  update, search, or comment on issues or pages.
---
# Atlas CLI

## Core rule

Use `atlas` via the Shell tool for all Atlassian operations. Do NOT use Docker MCP or WebFetch for Atlassian URLs.

All `atlas` commands require network access. Always pass `required_permissions: ["full_network"]` to the Shell tool.

## Discover commands and flags

Run `--help` to discover available subcommands and flags dynamically:

- `atlas --help` -- list top-level groups (jira, conf)
- `atlas jira --help` / `atlas conf --help` -- list subcommands
- `atlas jira create --help` -- list all flags for a subcommand

Always check `--help` before assuming a flag doesn't exist. New flags are added regularly.

## URL parsing

When given an Atlassian URL like `https://X.atlassian.net/browse/PROJ-123`, extract the issue key (`PROJ-123`) and run `atlas jira get PROJ-123`.

For Confluence URLs like `https://X.atlassian.net/wiki/spaces/SPACE/pages/123456`, extract the page ID (`123456`) and run `atlas conf get 123456`.

## Jira quick reference

- Get issue: `atlas jira get <KEY>` (add `--comments` for comments)
- Search: `atlas jira search "<JQL>" --limit 10` (add `--story-points`, `--parent` for extra columns)
- Children: `atlas jira children <KEY> --story-points` (recursive epic/feature traversal)
- Parent: `atlas jira parent <KEY>` (walk up the hierarchy)
- Fields: `atlas jira fields --search "story"` (discover custom field IDs)
- Create: `atlas jira create --project PROJ --type Story --summary "..." --parent PROJ-100 --ac "..."`
- Update: `atlas jira update <KEY> --summary "..." --description "..." --ac "..."`
- `--ac` and `--story-points` need `acceptance_criteria_field` and `story_points_field` in the atlas config. Discover ids with `atlas jira fields --search`. A Jira search needs a restriction, such as a project clause.
- Comment: `atlas jira comment <KEY> "comment text"`
- Transitions: `atlas jira transitions <KEY>` then `atlas jira transition <KEY> <ID>`

## Confluence quick reference

- Get page: `atlas conf get <PAGE-ID>`
- Search: `atlas conf search "query" --space SPACE`
- Page tree: `atlas conf tree <SPACE-KEY>`
- Create: `atlas conf create --space SPACE --title "..." --body "..."`
- Update: `atlas conf update <PAGE-ID> --title "..." --body "..."`
- Publish markdown with diagrams: `atlas conf publish <PAGE-ID> input.md --title "..."`
