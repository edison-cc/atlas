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

DEFAULT_STORY_POINTS_FIELD = "customfield_10031"


def get_story_points_field(config: dict | None = None) -> str:
    """Return the configured story-points custom field ID, or the default."""
    if config and "story_points_field" in config:
        return config["story_points_field"]
    for path in CONFIG_PATHS:
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            if "story_points_field" in data:
                return data["story_points_field"]
    return DEFAULT_STORY_POINTS_FIELD


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
