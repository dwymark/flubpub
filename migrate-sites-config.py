#!/usr/bin/env python3
"""One-off: convert a pre-JSON ~/.config/flubpub/sites.toml to sites.json.

This is a delete-after-use script, deliberately NOT a `flubpub` subcommand —
the registry is JSON now and this conversion happens exactly once per machine.
Run it, confirm sites.json looks right, then `rm` this file and the old .toml.

    python3 migrate-sites-config.py

Stdlib only; safe to run repeatedly (it refuses to clobber an existing
sites.json and leaves the .toml in place for you to delete yourself).
"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "flubpub"
TOML_PATH = CONFIG_DIR / "sites.toml"
JSON_PATH = CONFIG_DIR / "sites.json"


def main() -> int:
    if JSON_PATH.is_file():
        print(f"{JSON_PATH} already exists; nothing to migrate.")
        return 0
    if not TOML_PATH.is_file():
        print(f"No legacy {TOML_PATH} found; nothing to migrate.")
        return 0
    try:
        cfg = tomllib.loads(TOML_PATH.read_text())
    except tomllib.TOMLDecodeError as e:
        print(f"Could not parse {TOML_PATH}: {e}", file=sys.stderr)
        return 1
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"Migrated {TOML_PATH.name} -> {JSON_PATH}")
    print(f"Verify it, then: rm {TOML_PATH} migrate-sites-config.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
