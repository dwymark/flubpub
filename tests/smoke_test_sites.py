"""Smoke test: --site KEY resolution against ~/.config/flubpub/sites.toml.

Run with: PYTHONUNBUFFERED=1 uv run python3 tests/smoke_test_sites.py

Cases:
  1. `--site dwm` resolves via registry → dwm install dir
  2. `--site bj`  resolves via registry → bj install dir
  3. No flag, default=dwm in config → dwm install dir
  4. No flag, no default, no FLUBPUB_SITE → local HTTP mode (no shim ssh call)
  5. `--remote ...` always wins, even when --site is also passed
  6. FLUBPUB_SITE env var picks the site when --site is absent
  7. `--site` referencing an unknown key exits non-zero with a clear message
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.fakeremote import FakeRemote


def run(args: list[str], env: dict, expect_rc: int = 0) -> subprocess.CompletedProcess:
    proc = subprocess.run(["uv", "run", "flubpub", *args],
                          env=env, capture_output=True, text=True)
    if proc.returncode != expect_rc:
        sys.stderr.write(f"FAIL: {args} → rc={proc.returncode} (expected {expect_rc})\n")
        sys.stderr.write(f"stdout: {proc.stdout}\nstderr: {proc.stderr}\n")
        sys.exit(1)
    return proc


def write_config(home: Path, cfg: dict) -> None:
    cfg_dir = home / ".config" / "flubpub"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "sites.json").write_text(json.dumps(cfg, indent=2))


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    failures: list[str] = []

    fake_home = Path(tempfile.mkdtemp(prefix="flubpub-fake-home-"))

    with FakeRemote(verbose=True) as fr:
        fr.install("dwm"); fr.install("bj")

        both = {
            "default": "dwm",
            "sites": {
                "dwm": {"remote": f"root@fake.invalid:{fr.prefix}-dwm"},
                "bj": {"remote": f"root@fake.invalid:{fr.prefix}-bj"},
            },
        }
        write_config(fake_home, both)

        env = {**fr.env, "HOME": str(fake_home)}

        print("\n--- case 1: --site dwm ---")
        proc = run(["--site", "dwm", "list"], env)
        if f"dir={fr.actual_prefix}-dwm " not in proc.stdout:
            failures.append(f"site dwm: {proc.stdout!r}")

        print("\n--- case 2: --site bj ---")
        proc = run(["--site", "bj", "list"], env)
        if f"dir={fr.actual_prefix}-bj " not in proc.stdout:
            failures.append(f"site bj: {proc.stdout!r}")

        print("\n--- case 3: default falls through ---")
        proc = run(["list"], env)
        if f"dir={fr.actual_prefix}-dwm " not in proc.stdout:
            failures.append(f"default: {proc.stdout!r}")

        print("\n--- case 4: no default → local HTTP ---")
        write_config(fake_home, {
            "sites": {"dwm": {"remote": f"root@fake.invalid:{fr.prefix}-dwm"}}
        })
        # No remote/site/default → flubpub should try HTTP localhost:8000.
        # We expect non-zero rc (connection refused) but importantly NOT a
        # site-resolution error.
        proc = subprocess.run(["uv", "run", "flubpub", "list"],
                              env=env, capture_output=True, text=True)
        if proc.returncode == 0:
            failures.append("no-default: unexpectedly succeeded")
        if "Site '" in proc.stderr:
            failures.append(f"no-default: should not mention sites, got {proc.stderr!r}")

        print("\n--- case 5: --remote overrides --site ---")
        proc = run(["--remote", fr.remote_spec("bj"),
                    "--site", "dwm", "list"], env)
        if f"dir={fr.actual_prefix}-bj " not in proc.stdout:
            failures.append(f"--remote precedence: {proc.stdout!r}")

        print("\n--- case 6: FLUBPUB_SITE env var ---")
        write_config(fake_home, {
            "sites": {
                "dwm": {"remote": f"root@fake.invalid:{fr.prefix}-dwm"},
                "bj": {"remote": f"root@fake.invalid:{fr.prefix}-bj"},
            }
        })
        env_with_site = {**env, "FLUBPUB_SITE": "bj"}
        proc = run(["list"], env_with_site)
        if f"dir={fr.actual_prefix}-bj " not in proc.stdout:
            failures.append(f"FLUBPUB_SITE: {proc.stdout!r}")

        print("\n--- case 7: unknown site key fails cleanly ---")
        proc = subprocess.run(["uv", "run", "flubpub", "--site", "nosuch", "list"],
                              env=env, capture_output=True, text=True)
        if proc.returncode == 0:
            failures.append("unknown site: should have failed")
        if "not found" not in proc.stderr:
            failures.append(f"unknown site: stderr should explain; got {proc.stderr!r}")

        fr.print_transcript()

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All passed.")


if __name__ == "__main__":
    main()
