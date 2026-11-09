# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- `atlas conf publish --dry-run` renders diagrams and previews the page and attachments without Atlassian credentials.

### Fixed

- `atlas conf publish` stops before any writes if Mermaid rendering fails, reuses attachments for identical PNGs, and reports uploaded files on a page version conflict.

## [0.4.1] - 2026-11-05

### Fixed

- Package build with setuptools 77+. The MIT license is declared with the SPDX expression, so the duplicate license classifier is removed.

## [0.4.0] - 2026-11-05

### Changed

- Story points and acceptance criteria are optional. Set `story_points_field` and `acceptance_criteria_field` after discovering the ids with `atlas jira fields`. Atlas no longer assumes `customfield_10031` or `customfield_10046`.

### Fixed

- `atlas jira get --comments` requests the `comment` field. Jira Cloud does not include comments in `*navigable`.

## [0.3.0] - 2026-07-09

### Added

- `atlas conf get --comments` fetches and renders a Confluence page's comments (footer and inline) via a paginated `content/{id}/child/comment` call

### Fixed

- `atlas conf publish` markdown converter: soft-wrapped lines are now joined into a single paragraph/list item instead of one `<p>` per physical line, so inline spans that wrap across lines render correctly (CommonMark soft breaks)
- `atlas conf publish`: escaped pipes (`\|`) inside table cells no longer split the cell into extra columns
- `atlas conf publish`: inline code, emphasis, and links inside ATX headings are now parsed
- `atlas conf publish`: `<`, `>`, and `&` in inline text and inline code are HTML-escaped instead of being dropped as bogus HTML tags
- `atlas conf publish`: bold that wraps or begins with an inline code span keeps its `<strong>` wrapper
- `atlas conf publish`: an anchor link and an http link on the same line are now matched independently instead of being merged into one broken link

## [0.2.0] - 2026-05-01

### Added

- `jira parent` command to walk up the issue hierarchy
- Markdown table support in `markdown_to_adf` conversion
- Fenced code block support in `markdown_to_adf` conversion
- VS Code Copilot integration via `.github/copilot-instructions.md`, including a multi-step workflow example
- Agent-friendly CLI design section, command quick reference, and Windows install guide in the README
- Benchmark scope caveats and MCP context overhead documentation
- `uv.lock` checked into the repo for reproducible installs

### Fixed

- `atlas jira get` displays the parent for all issue types

### Changed

- README restructured for terminal, VS Code, and Cursor users with simplified Cursor setup guidance
- Benchmark files relocated into a top-level `benchmarks/` directory with the summary table moved to the top
- Windows install UX improvements

## [0.1.0] - 2025-06-01

### Added

- Jira commands: get, search, children, parent, fields, create, update, comment, transitions, transition
- Confluence commands: get, search, tree, create, update, publish
- ADF to Markdown bidirectional conversion
- Markdown to Confluence XHTML storage format conversion
- Configuration via `~/.config/atlas/config.json` or environment variables
- Cursor skill and workspace rule for agent integration
