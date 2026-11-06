"""Load Atlassian credentials from config file or environment variables."""

import json
import os
import sys
from pathlib import Path

CONFIG_PATHS = [
    Path.home() / ".config" / "atlas" / "config.json",
    Path.home() / ".config" / "confluence-publish" / "config.json",
]

REQUIRED_FIELDS = ["atlassian_email", "atlassian_api_token", "atlassian_base_url"]


def _blank_to_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_custom_field(key: str, config: dict | None = None) -> str | None:
    """Return a configured custom field ID, or None when it is unset or blank.

    A config dict is used as-is and is not merged with files on disk. Otherwise
    the value is read from the first config file that contains the key.
    """
    if config is not None:
        return _blank_to_none(config.get(key))
    for path in CONFIG_PATHS:
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            if key in data:
                return _blank_to_none(data[key])
    return None


def get_story_points_field(config: dict | None = None) -> str | None:
    """Return the configured story-points custom field ID, if any."""
    return get_custom_field("story_points_field", config)


def get_acceptance_criteria_field(config: dict | None = None) -> str | None:
    """Return the configured acceptance-criteria custom field ID, if any."""
    return get_custom_field("acceptance_criteria_field", config)


def warn_story_points_unconfigured() -> None:
    """Tell the user how to enable the story-points column."""
    print(
        "Story points field is not configured. "
        'Run `atlas jira fields --search "story"` and set '
        '"story_points_field" in '
        f"{CONFIG_PATHS[0]}.",
        file=sys.stderr,
    )


def require_acceptance_criteria_field() -> str:
    """Return the acceptance-criteria field ID, or exit if it is not configured."""
    field_id = get_acceptance_criteria_field()
    if not field_id:
        print(
            "Acceptance criteria field is not configured. "
            'Run `atlas jira fields --search "acceptance"` and set '
            '"acceptance_criteria_field" in '
            f"{CONFIG_PATHS[0]}.",
            file=sys.stderr,
        )
        sys.exit(1)
    return field_id


def load_config() -> dict:
    """Load config with priority: env vars > ~/.config/atlas/ > ~/.config/confluence-publish/."""
    env_email = os.environ.get("ATLASSIAN_EMAIL")
    env_token = os.environ.get("ATLASSIAN_API_TOKEN")
    env_url = os.environ.get("ATLASSIAN_BASE_URL")

    if env_email and env_token and env_url:
        return {
            "atlassian_email": env_email,
            "atlassian_api_token": env_token,
            "atlassian_base_url": env_url.rstrip("/"),
        }

    for path in CONFIG_PATHS:
        if path.exists():
            with open(path) as f:
                config = json.load(f)
            missing = [k for k in REQUIRED_FIELDS if k not in config]
            if missing:
                print(
                    f"Config at {path} missing fields: {', '.join(missing)}",
                    file=sys.stderr,
                )
                sys.exit(1)
            config["atlassian_base_url"] = config["atlassian_base_url"].rstrip("/")
            return config

    print(
        "No Atlassian credentials found. Set env vars "
        "(ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN, ATLASSIAN_BASE_URL) "
        f"or create {CONFIG_PATHS[0]}",
        file=sys.stderr,
    )
    sys.exit(1)
