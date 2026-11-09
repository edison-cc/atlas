# Contributing

## Setup

```bash
uv venv
uv pip install -e .
```

Configuration lives in `~/.config/atlas/config.json` or in `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`, and `ATLASSIAN_BASE_URL`. Do not commit a filled-in config or an API token.

## Tests

```bash
python tests/test_conf_publish.py
python tests/test_config.py
python tests/test_request_errors.py
python tests/test_jira_get.py
python tests/test_read_fidelity.py
python tests/test_write_output.py
python tests/test_benchmarks.py
```

These scripts run without pytest. The same commands run in CI on Python 3.10–3.13, followed by installation and CLI help smoke checks.

For performance measurements, follow [the benchmark protocol](benchmarks/README.md).

## Adding a command

Add a module in `atlas/commands/` named `jira_<name>.py` or `conf_<name>.py`. Export `register(subparser)` and `run(args, client)`. The CLI discovers it automatically.
