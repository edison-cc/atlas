"""Command auto-discovery for atlas CLI."""

import importlib
import pkgutil
from pathlib import Path


def discover_commands():
    """Yield (prefix, module) pairs for all command modules.

    Each module is expected to export:
      - register(subparser) -> None
      - run(args, client) -> None
    """
    package_dir = Path(__file__).parent
    for info in pkgutil.iter_modules([str(package_dir)]):
        module = importlib.import_module(f"{__name__}.{info.name}")
        if hasattr(module, "register") and hasattr(module, "run"):
            prefix = info.name.split("_", 1)[0]  # "jira" or "conf"
            yield prefix, module
