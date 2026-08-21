#!/usr/bin/env python3
"""Bump the version in pyproject.toml, stamp CHANGELOG.md, and create a git tag.

Usage:
    python scripts/bump_version.py 0.2.0
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"


def bump(new_version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", new_version):
        sys.exit(f"Invalid version: {new_version!r}  (expected N.N.N)")

    # --- pyproject.toml ---
    text = PYPROJECT.read_text()
    updated, count = re.subn(
        r'^(version\s*=\s*)"[^"]+"',
        rf'\1"{new_version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        sys.exit("Could not find version in pyproject.toml")
    PYPROJECT.write_text(updated)
    print(f"pyproject.toml → {new_version}")

    # --- CHANGELOG.md ---
    if CHANGELOG.exists():
        cl = CHANGELOG.read_text()
        heading = f"## [{new_version}] - {date.today().isoformat()}"
        cl = cl.replace("## [Unreleased]", f"## [Unreleased]\n\n{heading}", 1)
        CHANGELOG.write_text(cl)
        print(f"CHANGELOG.md   → {new_version} ({date.today()})")

    # --- git commit + tag ---
    tag = f"v{new_version}"
    subprocess.run(["git", "add", "pyproject.toml", "CHANGELOG.md"], check=True, cwd=ROOT)
    subprocess.run(["git", "commit", "-m", f"release {tag}"], check=True, cwd=ROOT)
    subprocess.run(["git", "tag", tag], check=True, cwd=ROOT)
    print(f"\nCreated commit and tag {tag}")
    print(f"Run:  git push --follow-tags")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(f"Usage: {sys.argv[0]} <version>")
    bump(sys.argv[1])
