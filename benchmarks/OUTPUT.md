# Atlas CLI Context Reduction Benchmarks

Measured on 2026-03-13 against live Jira Cloud and Confluence Cloud APIs (your-site.atlassian.net).

> **Note on the sample data:** the issue content shown in the examples below is illustrative
> placeholder data, not the issue that was actually measured. All character and token counts in
> this document are from the original measured issue, so re-counting the sample text printed here
> will give slightly lower numbers (roughly 5-8% for the single-issue examples). The relative
> reductions and the comparison between layers are unaffected.

## Measurement status

These are historical reported counts, not independently reproduced results for the
current release. Original payloads are unavailable; the examples below are
illustrative. The old methodology conflated bytes and characters and estimated
tokens as characters / 4. No tokenizer-based token saving was measured.
The recorded totals give **93.75% (about 94%)**, not 96%, arithmetically.
However, raw API baselines are absent for transitions and Confluence get, so this
is not a matched-workload reduction. No validated raw API saving is claimed.
See [the new protocol](README.md) before publishing replacement results.

## Summary

The historical MCP/Atlas totals imply about 60% fewer reported characters.
They do not establish an actual token or session-context reduction.

This document measures **per-call output size** (how much each tool result adds to the conversation). For **schema loading cost** (MCP infrastructure overhead per turn + on-demand schema reads that accumulate in conversation history), see [SCHEMA.md](SCHEMA.md). For **execution latency**, see [LATENCY.md](LATENCY.md).

| Layer | Reported total | Tokens (approx) | vs Atlas |
|-------|-------------------|------------------|----------|
| Raw Atlassian API | 41,567 chars | ~10,391 | 16x larger |
| Docker MCP | 6,421 chars | ~1,605 | 2.5x larger |
| **Atlas CLI** | **2,597 chars** | **~649** | **baseline** |

## Example Outputs: `jira get issue PROJ-123`

The same issue fetched through all three layers. This is what enters the model context.
The counts in each heading are from the measured issue; the body text shown is placeholder data
(see the note at the top of this file).

### Raw Atlassian API (27,788 chars, ~6,947 tokens)

```json
{
  "expand": "renderedFields,names,schema,operations,editmeta,changelog,...",
  "id": "10001234",
  "self": "https://your-site.atlassian.net/rest/api/3/issue/10001234",
  "key": "PROJ-123",
  "fields": {
    "parent": {
      "id": "10001200",
      "key": "PROJ-100",
      "self": "https://your-site.atlassian.net/rest/api/3/issue/10001200",
      "fields": {
        "summary": "Backlog",
        "status": {
          "self": "https://your-site.atlassian.net/rest/api/3/status/10019",
          "description": "",
          "iconUrl": "https://your-site.atlassian.net/images/icons/statuses/generic.png",
          "name": "New",
          "id": "10019",
          "statusCategory": {
            "self": "https://your-site.atlassian.net/rest/api/3/statuscategory/2",
            "id": 2,
            "key": "new",
            "colorName": "blue-gray",
            "name": "To Do"
          }
        },
        "priority": {
          "self": "https://your-site.atlassian.net/rest/api/3/priority/10022",
          "iconUrl": "https://your-site.atlassian.net/images/icons/priorities/medium.svg",
          "name": "Medium",
          "id": "10022"
        },
        "issuetype": { "...": "..." }
      }
    },
    "statusCategory": { "self": "...", "id": 4, "key": "indeterminate", "colorName": "yellow", "name": "In Progress" },
    "resolution": null,
    "customfield_11720": null,
    "customfield_11962": null,
    "customfield_10630": { "self": "...", "value": "N/A", "id": "15030" },
    "customfield_10631": { "self": "...", "value": "N/A", "id": "21123" },
    "customfield_11961": null,
    "customfield_11710": null,
    "customfield_11955": null,
    "customfield_12802": null,
    "...": "(60+ more fields, most null or irrelevant)",
    "assignee": {
      "self": "https://your-site.atlassian.net/rest/api/3/user?accountId=000000...",
      "accountId": "000000:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "emailAddress": "alice.smith@example.com",
      "avatarUrls": {
        "48x48": "https://avatar-placeholder.example.com/AS-0.png",
        "24x24": "https://avatar-placeholder.example.com/AS-0.png",
        "16x16": "https://avatar-placeholder.example.com/AS-0.png"
      },
      "displayName": "Alice Smith",
      "active": true,
      "timeZone": "Asia/Jerusalem",
      "accountType": "atlassian"
    },
    "description": {
      "version": 1,
      "type": "doc",
      "content": [
        { "type": "heading", "attrs": { "level": 1 }, "content": [{ "type": "text", "text": "Import Job Requirement: 7f3a91d2..." }] },
        { "type": "paragraph", "content": [{ "type": "text", "text": "Component:", "marks": [{ "type": "strong" }] }, { "type": "text", "text": " WEB" }] },
        "... (entire ADF JSON tree for every paragraph, heading, list item)"
      ]
    },
    "summary": "Example task summary",
    "...": "(continues for 27,788 total chars)"
  }
}
```

### Docker MCP (1,748 chars, ~437 tokens)

```json
{
  "id": "10001234",
  "key": "PROJ-123",
  "summary": "Example task summary",
  "description": "# Import Job Requirement: 7f3a91d2-4c8e-4b1a-9e07-2d5fb6c1a840\n\n \n\n**Component:** WEB\n\n**Priority:** 1 🔴 HIGH\n\n**Region:** US\n\n \n\n## Technical Specifications\n\n  - **Test Environment:* Staging cluster / shared queue\n\n  - **Data Volume:* Moderate\n\n \n\n## Component-Specific Requirements\n\n  - **Input Format:* CSV files of average size and column count\n\n  - **Retry Behavior:* Exponential backoff\n\n  - **Expected Batches:* 5\n\n  - **Provider:* Acme\n\n  - **Delivery Channel:* SFTP\n\n \n\n## Notes\n\n📝 **Note:** For WEB requirements, input scenarios and environment conditions not explicitly defined can be adapted in coordination with the assigned provider.\n\n \n\n## Metadata\n\n  - **Created:* 2026-01-08 09:41:12.114302\n\n  - **Target Sprint:* 24.2",
  "status": {
    "name": "In Review",
    "category": "In Progress",
    "color": "yellow"
  },
  "issue_type": {
    "name": "Sub-task"
  },
  "priority": {
    "name": "Highest"
  },
  "assignee": {
    "display_name": "Alice Smith",
    "name": "Alice Smith",
    "email": "alice.smith@example.com",
    "avatar_url": "https://avatar-placeholder.example.com/AS-0.png"
  },
  "reporter": {
    "display_name": "Bob Jones",
    "name": "Bob Jones",
    "email": "bob.jones@example.com",
    "avatar_url": "https://avatar-placeholder.example.com/BJ-0.png"
  },
  "labels": ["PROJ-7897f3a91d2-4c8e-4b1a-9e07-2d5", "high-priority", "staging-cluster-shared-queue", "web", "site-us"],
  "created": "2026-02-09T05:35:12.347-0500",
  "updated": "2026-03-08T03:53:14.096-0400"
}
```

### Atlas CLI (1,120 chars, ~280 tokens)

```
## PROJ-123: Example task summary

- **Status**: In Review | **Type**: Sub-task | **Priority**: Highest
- **Assignee**: Alice Smith | **Reporter**: Bob Jones
- **Labels**: PROJ-7897f3a91d2-4c8e-4b1a-9e07-2d5, high-priority, staging-cluster-shared-queue, web, site-us
- **Created**: 2026-02-09 | **Updated**: 2026-03-08

### Description

# Import Job Requirement: 7f3a91d2-4c8e-4b1a-9e07-2d5fb6c1a840

**Component:** WEB
**Priority:** 1 🔴 HIGH
**Region:** US

## Technical Specifications
- **Test Environment:** Staging cluster / shared queue
- **Data Volume:** Moderate

## Component-Specific Requirements
- **Input Format:** CSV files of average size and column count
- **Retry Behavior:** Exponential backoff
- **Expected Batches:** 5
- **Provider:** Acme
- **Delivery Channel:** SFTP

## Notes
📝 **Note:** For WEB requirements, input scenarios and environment conditions not explicitly defined can be adapted in coordination with the assigned provider.

## Metadata
- **Created:** 2026-01-08 09:41:12.114302
- **Target Sprint:** 24.2
```

### What gets eliminated

The context bloat in the raw API and Docker MCP comes from:

- **Avatar URLs**: 150+ chars each, 4 size variants per user, purely visual
- **Self-links**: `"self": "https://your-site.atlassian.net/rest/api/3/..."` on every object
- **Null custom fields**: `"customfield_11720": null` repeated 40+ times
- **Nested status metadata**: category, color, icon URL -- the model only needs the status name
- **ADF JSON tree**: description as deeply nested JSON AST instead of plain text
- **Timestamps with timezone**: `"2026-02-09T05:35:12.347-0500"` vs `2026-02-09`
- **Duplicate names**: assignee.display_name + assignee.name + assignee.email (only display_name is needed)

## Per-Operation Comparison

### 1. Jira Get Issue (PROJ-123)

A Sub-task with description, labels, assignee, sprint info.

| Source | Chars | Tokens (approx) | Reduction vs Atlas |
|--------|-------|------------------|-------------------|
| Raw API | 27,788 | ~6,947 | 25x |
| Docker MCP | 1,748 | ~437 | 1.6x |
| **Atlas CLI** | **1,120** | **~280** | **baseline** |

Why the difference:
- Raw API includes 60+ fields (schema, transitions, changelog, avatar URLs, ADF JSON trees, self-links, expand metadata)
- Docker MCP strips most fields but keeps nested JSON objects (status.category, status.color, assignee.email, assignee.avatar_url)
- Atlas CLI emits only what the model needs: flat Markdown with status, type, priority, assignee name, labels, dates, and description as plain text

### 2. Jira Search (5 issues, JQL: `updated >= -7d`)

| Source | Chars | Tokens (approx) | Reduction vs Atlas |
|--------|-------|------------------|-------------------|
| Raw API | 6,830 | ~1,707 | 9.1x |
| Docker MCP | 2,087 | ~522 | 2.8x |
| **Atlas CLI** | **752** | **~188** | **baseline** |

Why the difference:
- Docker MCP returns nested objects per issue (status.category, status.color, assignee.email, assignee.avatar_url, pagination token)
- Atlas CLI returns a Markdown table: `| Key | Summary | Status | Assignee | Updated |`
- Per-issue overhead: Docker MCP ~400 chars/issue, Atlas ~100 chars/issue

### 3. Jira Transitions (PROJ-123)

| Source | Chars | Tokens (approx) |
|--------|-------|------------------|
| Docker MCP | 78 | ~20 |
| **Atlas CLI** | **148** | **~37** |

Atlas is larger here because it adds a "To Status" column that Docker MCP omits. This is intentional -- the target status is the most useful piece of information when deciding which transition to take.

### 4. Confluence Get Page (987923264)

| Source | Chars | Tokens (approx) | Reduction vs Atlas |
|--------|-------|------------------|-------------------|
| Docker MCP | 290 | ~73 | 3.1x |
| **Atlas CLI** | **95** | **~24** | **baseline** |

Docker MCP includes nested space object, empty arrays, URL. Atlas emits one header + one metadata line.

### 5. Confluence Search (5 results, query: "design")

| Source | Chars | Tokens (approx) | Reduction vs Atlas |
|--------|-------|------------------|-------------------|
| Raw API | 6,949 | ~1,737 | 14.4x |
| Docker MCP | 2,218 | ~555 | 4.6x |
| **Atlas CLI** | **482** | **~121** | **baseline** |

Why the difference:
- Docker MCP returns full content snippets with `@@@hl@@@` highlight markers, URLs, empty arrays, nested space objects per result
- Atlas CLI returns a Markdown table: `| Title (ID) | Space | Type | Updated |`
- Per-result overhead: Docker MCP ~440 chars/result, Atlas ~80 chars/result

## Reproducing replacement results

The original measurements cannot be reconstructed from the placeholder examples.
Use [the benchmark protocol](README.md) and `benchmark_output.py` with saved,
reviewed outputs for the same resources, fields, and result limits. Keep these
historical tables separate from new results.

Output sizes exclude invocation arguments, schema/help discovery, and agent tool
envelopes. They therefore do not establish total session context savings. Raw API
responses are a reference baseline; they are not normally sent directly to an agent.
