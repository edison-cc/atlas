"""Atlas CLI - Compact Jira and Confluence command-line interface."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("atlassian-atlas")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
