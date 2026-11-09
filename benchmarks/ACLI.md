# Atlas and Atlassian CLI

## Command coverage

Inventory from the installed Atlassian CLI (ACLI) 1.3.40-stable and the Atlas
checkout containing the read, publish, and JSON changes. Counts cover leaf
commands listed in the recursive `jira --help` and `conf --help` or
`confluence --help` trees. Authentication, help, top-level administration,
Guard, and Rovo Dev are outside these counts. Separate visible command names
count separately even when their actions overlap.

| Scope | Atlas | ACLI 1.3.40 |
| --- | ---: | ---: |
| Jira | 10 | 60 |
| Confluence | 6 | 10 |
| Total | 16 | 70 |

| Workflow | Atlas | ACLI 1.3.40 |
| --- | --- | --- |
| Jira issue reads and JQL | Markdown by default, JSON on supported reads, issue fields, search, and dedicated parent and recursive children commands | Issue view, JQL and saved filters, selected fields, JSON and CSV search output, counts, and explicit pagination |
| Jira issue changes | Create, update, add a comment, list available transitions, and transition by ID | Create, edit, bulk create and transition, assign, clone, archive, delete, and manage comments, links, watchers, and attachments |
| Jira administration | Find field IDs by name | Manage fields, projects, boards, sprints, filters, and dashboards |
| Confluence pages | Read Markdown or storage markup, search with CQL, browse a space tree, create and update pages, and publish Markdown with rendered Mermaid attachments | View pages by ID in storage, ADF, or view format, with optional metadata and direct children |
| Confluence spaces and blogs | Work with pages in a selected space | List, view, create, update, archive, and restore spaces, plus list, view, and create blog posts |

The command counts describe the exposed CLI surface. From the Atlas source, the
two product clients use 17 distinct HTTP method and route-template combinations
(nine Jira, eight Confluence). ACLI's help describes actions rather than the
REST calls they make, so this inventory compares supported workflows and leaves
ACLI's endpoint count unspecified.

Sources for the documented Jira features include the [ACLI command reference](https://developer.atlassian.com/cloud/acli/reference/commands/),
[search reference](https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-search/),
and [changelog](https://developer.atlassian.com/cloud/acli/changelog/).
The Confluence inventory comes from the installed binary's
`acli confluence --help` tree.

## Live Jira benchmark

On November 8, 2026 (Pacific time), we compared a preview build of Atlas 0.4.1
with ACLI 1.3.40-stable on one Atlassian Cloud site from an Apple M3 Max Mac.
Atlas used an API token and ACLI used OAuth. The timed interval covers CLI
startup, the authenticated request path, and capture of the JSON output.

| Jira workload | Atlas p50 / p95 (ms) | ACLI p50 / p95 (ms) | Atlas / ACLI stdout (median bytes) |
| --- | ---: | ---: | ---: |
| Issue metadata | 283.5 / 361.9 | 838.8 / 916.0 | 440 / 1,005 |
| Issue with a short description | 263.6 / 318.0 | 711.1 / 873.8 | 577 / 1,295 |
| Issue with a longer description | 268.3 / 359.0 | 810.1 / 981.9 | 1,389 / 3,240 |
| Issue with a comment | 272.5 / 314.5 | 809.5 / 925.5 | 3,238 / 4,807 |
| JQL search, 1 row | 331.2 / 445.5 | 1,037.5 / 1,160.0 | 604 / 1,170 |
| JQL search, 10 rows | 323.1 / 380.1 | 936.6 / 1,150.7 | 4,586 / 11,010 |
| JQL search, 16 rows | 332.6 / 407.2 | 1,077.3 / 1,268.7 | 7,274 / 17,604 |

Across these cases, Atlas had 63–69% lower median latency and 33–59% fewer
JSON stdout bytes. All 210 measured pairs matched and all 420 commands
succeeded. Each workload used two warm-up pairs, followed by 30 measured
pairs with the execution order alternating.

We checked issue IDs, keys, requested fields, and the order of search
results. Status was compared by ID and name. Descriptions were compared as
ADF, and the comment case checked the total plus comment IDs, ADF bodies, and
timestamps. The two descriptions had 25 and 398 rendered characters, the
comment case contained one comment, and the search matched 16 visible issues.
Byte counts include each CLI's native JSON envelope and whitespace.

The measured Atlas tree combined [the JSON output change](https://github.com/edison-cc/atlas/commit/e011e0f6cfb49fd2254676a8c997ef00e70af9c4)
with [the startup and benchmark change](https://github.com/edison-cc/atlas/commit/be69a152c85ae9664148e034ea9670c730f625a5).
The [anonymized Jira report](results/atlas-acli-2026-11-08.json) records the exact
tree ID and individual samples. The run did not instrument HTTP request counts.

## Live Confluence benchmark

A separate run on November 8, 2026 (Pacific time) used the same Mac, site, and
CLI builds. Atlas used an API token and ACLI used its Confluence OAuth login.
Both requested JSON with the storage body. The validator compared the page
ID, title, and exact storage string for every pair.

| Confluence workload | Atlas p50 / p95 (ms) | ACLI p50 / p95 (ms) | Atlas / ACLI stdout (median bytes) |
| --- | ---: | ---: | ---: |
| Page with a 2.2 KB storage body | 260.8 / 325.7 | 990.2 / 1,153.2 | 2,473 / 4,007 |
| Page with a 16.3 KB storage body | 230.9 / 284.8 | 1,016.3 / 1,188.2 | 16,921 / 23,762 |

Atlas had 74–77% lower median latency and 29–38% fewer JSON stdout bytes
across the two page reads. All 60 measured pairs matched and all 120 commands
succeeded. Each case used two warm-up pairs and 30 measured pairs. Timing
includes the configured authentication and request paths. Output byte counts
include the CLI-specific JSON envelopes and whitespace.

The [anonymized Confluence report](results/atlas-acli-confluence-2026-11-08.json)
contains the individual samples. The measured Confluence workload covers
page reads by ID.

## Reproduce the comparison

Use an Atlas build with schema version 1 JSON output and an ACLI build signed
in to the same Jira site. Set the same requested fields on both sides. If Atlas
is configured to append custom fields to issue reads, include those field IDs
in the case too.

Create a local JSON file with your own fixture identifiers. For example, this
manifest expects the first ten results of a stable query in a test project.

```json
[
  {
    "name": "Issue with description",
    "kind": "issue",
    "key": "DEMO-1",
    "fields": ["key", "summary", "status", "description"]
  },
  {
    "name": "JQL search (10 rows)",
    "kind": "search",
    "jql": "project = DEMO ORDER BY key ASC",
    "fields": ["key", "summary", "status"],
    "limit": 10,
    "count": 10
  }
]
```

Use `comment` in the issue's field list to compare embedded comments. For a
Confluence read, use `{"name": "Confluence page", "kind": "page", "id": "123456"}`
and sign ACLI in to Confluence separately. The runner compares the page ID,
title, and storage body.

```bash
python -m benchmarks.benchmark_acli --cases /path/to/local-cases.json \
  --atlas /path/to/atlas --atlas-revision "$(git rev-parse HEAD)" \
  --acli acli --output /tmp/atlas-acli.json
```

Use the source revision of the Atlas executable you actually pass. The runner
saves timings, output byte counts, labels, and match status. It leaves issue
keys, page IDs, JQL, and response contents in memory. Use generic case labels
if the report will be shared.
