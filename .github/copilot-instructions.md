## Core policy

- For all Jira and Confluence operations, use the `atlas` CLI through shell execution.
- Do not use Atlassian MCP tools/servers.
- If both MCP and `atlas` are available, always choose `atlas`.

## Routing

### Jira
- Read issue: `atlas jira get <KEY>` (add `--comments` for comments)
- Search issues: `atlas jira search "<JQL>" --limit 10` (add `--story-points`, `--parent` for extra columns)
- Children: `atlas jira children <KEY> --story-points` (recursive epic/feature traversal)
- Parent: `atlas jira parent <KEY>` (walk up the hierarchy)
- Fields: `atlas jira fields --search "story"` (discover custom field IDs)
- Create issue: `atlas jira create --project PROJ --type Story --summary "..." --parent PROJ-100 --ac "..."`
- Update issue: `atlas jira update <KEY> --summary "..." --description "..." --ac "..."`
- `--ac` and `--story-points` need `acceptance_criteria_field` and `story_points_field` in the atlas config. Discover ids with `atlas jira fields --search`. A Jira search needs a restriction, such as a project clause.
- Comment: `atlas jira comment <KEY> "comment text"`
- List transitions: `atlas jira transitions <KEY>`
- Transition issue: `atlas jira transition <KEY> <TRANSITION_ID>`

### Confluence
- Read page: `atlas conf get <PAGE_ID>`
- Search pages: `atlas conf search "<query>" --space <SPACE_KEY>`
- Tree: `atlas conf tree <SPACE_KEY>`
- Create page: `atlas conf create --space <SPACE_KEY> --title "..." --body "..."`
- Update page: `atlas conf update <PAGE_ID> --title "..." --body "..."`
- Publish markdown: `atlas conf publish <PAGE_ID> <FILE.md> --title "..."`

## Multi-step workflow example

When asked to find child stories under a feature/epic **by name** (not key), use two steps:

```bash
# Step 1 – Resolve the name to a Jira key
atlas jira search 'summary ~ "User Profile Redesign"' --limit 5 --parent

# Step 2 – Query children of that key, filtering by status
atlas jira search 'parent = PROJ-321 AND status = "Completed"' --story-points --limit 50
```

Generalized pattern:

```bash
# Find the parent issue by name
atlas jira search 'summary ~ "<FEATURE_NAME>"' --limit 5 --parent

# Then search its children with any JQL filter
atlas jira search 'parent = <KEY> AND status = "<STATUS>"' --story-points --limit 50
```

## Flag discovery requirement

Before write operations, discover current flags with help:

- `atlas jira create --help`
- `atlas jira update --help`
- `atlas conf create --help`
- `atlas conf update --help`
- `atlas conf publish --help`

Do not assume stale flag syntax.

## Safety

- Do not invent issue keys/page IDs.
- Ask for required missing inputs before write operations.
- Prefer read commands first when context is unclear.
