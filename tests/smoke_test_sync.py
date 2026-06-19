"""Smoke test: `sync` skips unchanged pages and rebuilds once per batch.

Run with: PYTHONUNBUFFERED=1 uv run python3 tests/smoke_test_sync.py

`sync` reconciles a remote site against content/<key>/. This exercises the
two perf behaviors added to it:

  - rebuild deferral: every push/revise/set-index runs with --no-rebuild and
    sync issues a single `rebuild` at the end (and none at all when nothing
    changed);
  - change detection: a per-site .sync-state.json caches each page's content
    digest, so a second sync with no edits skips every page.

The remote side is the default (stub) ssh shim — it records calls but does
not mutate the fake install's data/pages.json. That is exactly what we want:
the test owns the "remote state" by writing data/pages.json directly, and
asserts on what sync *decides* to do (its stdout report + the call transcript).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.fakeremote import FakeRemote

REPO = Path(__file__).resolve().parent.parent
FLUBPUB = REPO / ".venv" / "bin" / "flubpub"


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)
            print(f"  FAIL: {msg}")

    fake_home = Path(tempfile.mkdtemp(prefix="flubpub-sync-home-"))
    fake_repo = Path(tempfile.mkdtemp(prefix="flubpub-sync-repo-"))
    (fake_repo / ".git").mkdir()
    content_test = fake_repo / "content" / "test"
    content_test.mkdir(parents=True)
    (content_test / "_manifest.toml").write_text('index = "home.md"\n')
    (content_test / "home.md").write_text("# Home\n\nwelcome\n")
    (content_test / "a.md").write_text("# A\n\nalpha body\n")
    (content_test / "b.md").write_text("# B\n\nbeta body\n")

    with FakeRemote(verbose=False) as fr:
        fr.install("test")
        remote_pages = fr.install_path("test") / "data" / "pages.json"
        cfg = fake_home / ".config" / "flubpub"
        cfg.mkdir(parents=True)
        (cfg / "sites.json").write_text(json.dumps({
            "content_root": str(fake_repo),
            "sites": {"test": {"remote": fr.remote_spec("test"), "port": 8099}},
        }, indent=2))

        last = {"proc": None}

        def sync(*extra: str, extra_env: dict | None = None) -> str:
            fr.transcript_path.write_text("")  # snapshot calls per-run
            env = {**fr.env, "HOME": str(fake_home)}
            if extra_env:
                env.update(extra_env)
            proc = subprocess.run(
                [str(FLUBPUB), "--no-mirror", "--site", "test", "sync", *extra],
                cwd=str(fake_repo), env=env, capture_output=True, text=True,
            )
            last["proc"] = proc
            if proc.returncode != 0:
                sys.stderr.write(f"sync rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}\n")
                sys.exit(1)
            return proc.stdout

        import shlex as _shlex

        def _flubpub_calls() -> list[list[str]]:
            """Token lists of every remote `uv run flubpub` call this run, with
            the leading `--server <url>` pair stripped. The capability probe
            (`rebuild --help`) is excluded — it's not real work."""
            out = []
            for e in fr.read_transcript():
                p = e.raw.get("parsed", {})
                if e.raw.get("kind") != "flubpub" or not p.get("args"):
                    continue
                toks = _shlex.split(p["args"])
                i = 0
                while i < len(toks) and toks[i] == "--server":
                    i += 2
                toks = toks[i:]
                if "--help" in toks:
                    continue
                if toks:
                    out.append(toks)
            return out

        def remote_flubpub_cmds() -> list[str]:
            return [c[0] for c in _flubpub_calls()]

        def saw_no_rebuild_flag() -> bool:
            return any("--no-rebuild" in c for c in _flubpub_calls())

        def cleanup_calls() -> int:
            """Count the `rm -rf /tmp/flubpub-upload-*` sweeps this run (the
            upload mkdirs also mention flubpub-upload, so match the rm)."""
            n = 0
            for e in fr.read_transcript():
                if e.raw.get("kind") == "bash" and \
                        "rm -rf /tmp/flubpub-upload" in e.raw.get("remote_cmd", ""):
                    n += 1
            return n

        state_file = content_test / ".sync-state.json"

        # --- run 1: empty remote → push everything, set index, one rebuild ---
        print("--- run 1: initial sync (remote empty) ---")
        out = sync()
        check("pushed   (2)" in out, "run1: expected 2 pushes")
        check("skipped  (0)" in out, "run1: expected 0 skips")
        cmds = remote_flubpub_cmds()
        check(cmds.count("rebuild") == 1, f"run1: expected exactly 1 rebuild, got {cmds}")
        check("set-index" in cmds, "run1: expected a set-index call")
        check(saw_no_rebuild_flag(),
              "run1: deferred path should forward --no-rebuild to the remote")
        # 2 pushes + 1 set-index uploaded, but cleanup is deferred to one sweep.
        check(cleanup_calls() == 1,
              f"run1: expected exactly 1 tmp cleanup sweep, got {cleanup_calls()}")
        check(state_file.is_file(), "run1: .sync-state.json not written")
        st = json.loads(state_file.read_text())
        check(set(st.get("pages", {})) == {"a", "b"},
              f"run1: state should track a,b; got {list(st.get('pages', {}))}")
        check(st.get("index") is not None, "run1: index digest not recorded")

        # Simulate the pushes having landed on the remote.
        remote_pages.write_text(json.dumps([
            {"slug": "a", "title": "A"}, {"slug": "b", "title": "B"},
        ]))

        # --- run 2: no edits → skip both pages, skip index, NO rebuild ---
        print("--- run 2: re-sync with no changes ---")
        out = sync()
        check("pushed   (0)" in out, "run2: expected 0 pushes")
        check("revised  (0)" in out, "run2: expected 0 revises")
        check("skipped  (2)" in out, "run2: expected 2 skips")
        cmds = remote_flubpub_cmds()
        check("rebuild" not in cmds, f"run2: expected NO rebuild, got {cmds}")
        check("revise" not in cmds and "push" not in cmds,
              f"run2: expected no push/revise calls, got {cmds}")

        # --- run 3: edit one page → revise just that one, skip the other ---
        print("--- run 3: edit a.md, re-sync ---")
        (content_test / "a.md").write_text("# A\n\nalpha body EDITED\n")
        out = sync()
        check("revised  (1)" in out, "run3: expected exactly 1 revise")
        check("skipped  (1)" in out, "run3: expected exactly 1 skip")
        cmds = remote_flubpub_cmds()
        check(cmds.count("revise") == 1, f"run3: expected 1 revise call, got {cmds}")
        check(cmds.count("rebuild") == 1, f"run3: expected 1 rebuild, got {cmds}")

        # --- run 4: stability — no further edits → all skip again ---
        print("--- run 4: re-sync again, expect all skipped ---")
        out = sync()
        check("skipped  (2)" in out, "run4: expected 2 skips (digests stable)")
        check("rebuild" not in remote_flubpub_cmds(),
              "run4: expected NO rebuild on unchanged re-sync")

        # --- run 5: --force re-revises everything despite the cache ---
        print("--- run 5: --force ignores the digest cache ---")
        out = sync("--force")
        check("revised  (2)" in out, "run5: --force should revise both pages")
        check("skipped  (0)" in out, "run5: --force should skip nothing")

        # --- run 6: legacy remote (no --no-rebuild) → graceful fallback ---
        # Simulates an un-redeployed VPS: the capability probe fails, so sync
        # must run in per-page-rebuild mode (no --no-rebuild forwarded, no final
        # `rebuild` command) rather than hard-failing like the real bug did.
        print("--- run 6: remote predating --no-rebuild ---")
        out = sync("--force", extra_env={"FAKE_REMOTE_LEGACY": "1"})
        check("revised  (2)" in out, "run6: legacy fallback should still revise both")
        check("predates --no-rebuild" in last["proc"].stderr,
              "run6: expected the legacy-remote note on stderr")
        check(not saw_no_rebuild_flag(),
              "run6: must NOT forward --no-rebuild to a legacy remote")
        check("rebuild" not in remote_flubpub_cmds(),
              "run6: must NOT call the `rebuild` command on a legacy remote")
        check(remote_flubpub_cmds().count("revise") == 2,
              f"run6: expected 2 revises, got {remote_flubpub_cmds()}")

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All passed.")


if __name__ == "__main__":
    main()
