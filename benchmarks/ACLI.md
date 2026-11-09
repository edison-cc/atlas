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
