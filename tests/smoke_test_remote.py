"""Smoke test: --remote spec parsing and routing, exercised through shims.

Run with: PYTHONUNBUFFERED=1 uv run python3 tests/smoke_test_remote.py

This verifies the CLI-side routing only — the shim stubs the remote-side
`uv run flubpub` invocation. To exercise the remote side end-to-end, set
FAKE_REMOTE_EXECUTE=1 (requires a server-per-install setup; TODO).

Cases:
  1. Legacy `--remote root@host` → install dir defaults to /opt/flubpub.
  2. Extended `--remote root@host:/opt/flubpub-dwm` → dwm install.
  3. Extended `--remote root@host:/opt/flubpub-bj` → bj install.
  4. `push` invokes scp to copy file (and refs) before the ssh exec.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.fakeremote import FakeRemote


def run(args: list[str], env: dict, expect_rc: int = 0) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["uv", "run", "flubpub", *args],
        env=env, capture_output=True, text=True,
    )
    if proc.returncode != expect_rc:
        sys.stderr.write(f"FAIL: {args} → rc={proc.returncode} (expected {expect_rc})\n")
        sys.stderr.write(f"stdout: {proc.stdout}\nstderr: {proc.stderr}\n")
        sys.exit(1)
    return proc


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    failures: list[str] = []

    with FakeRemote(verbose=True) as fr:
        fr.install("dwm")
        fr.install("bj")

        print("\n--- case 1: legacy --remote (no path) ---")
        proc = run(["--remote", "root@fake.invalid", "list"], fr.env)
        if f"dir={fr.actual_prefix} " not in proc.stdout:
            failures.append(f"legacy: stdout did not show default dir; got {proc.stdout!r}")

        print("\n--- case 2: extended --remote → dwm ---")
        proc = run(["--remote", fr.remote_spec("dwm"), "list"], fr.env)
        if f"dir={fr.actual_prefix}-dwm " not in proc.stdout:
            failures.append(f"dwm: stdout did not show dwm dir; got {proc.stdout!r}")

        print("\n--- case 3: extended --remote → bj ---")
        proc = run(["--remote", fr.remote_spec("bj"), "list"], fr.env)
        if f"dir={fr.actual_prefix}-bj " not in proc.stdout:
            failures.append(f"bj: stdout did not show bj dir; got {proc.stdout!r}")

        print("\n--- case 4: push uses scp + ssh ---")
        page = Path("/tmp/fake-page.md")
        page.write_text("# hello from a fake page\n")
        run(["--remote", fr.remote_spec("dwm"), "push", str(page),
             "--title", "Hello"], fr.env)

        entries = fr.read_transcript()
        ssh_entries = [e for e in entries if e.op == "ssh"]
        scp_entries = [e for e in entries if e.op == "scp"]

        print("\n--- transcript shape assertions ---")
        # 3 lists + 1 push (+ 1 cleanup ssh) = 5 ssh; push = 1 scp
        if len(ssh_entries) < 4:
            failures.append(f"expected ≥4 ssh calls, got {len(ssh_entries)}")
        if len(scp_entries) < 1:
            failures.append(f"expected ≥1 scp call, got {len(scp_entries)}")

        # Verify the dirs that the four list/push commands targeted.
        flubpub_dirs = [
            e.raw["parsed"]["remote_dir"]
            for e in ssh_entries
            if e.raw.get("kind") == "flubpub"
        ]
        expected = [
            fr.prefix,                # case 1
            f"{fr.prefix}-dwm",       # case 2
            f"{fr.prefix}-bj",        # case 3
            f"{fr.prefix}-dwm",       # case 4 (push)
        ]
        if flubpub_dirs[:4] != expected:
            failures.append(f"flubpub remote_dirs: {flubpub_dirs[:4]} != {expected}")

        # The scp from case 4 should have shipped to /tmp (shared, untranslated)
        scp = scp_entries[0]
        if not scp.raw["dst"].startswith("/tmp/flubpub-upload-"):
            failures.append(f"scp dst should be /tmp/flubpub-upload-...; got {scp.raw['dst']}")

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
