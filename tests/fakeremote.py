"""A fake-ssh harness for testing flubpub's `--remote` codepath without a VPS.

Usage:

    from tests.fakeremote import FakeRemote

    with FakeRemote() as fr:
        fr.install("dwm")
        fr.install("bj")
        # `flubpub` subprocesses spawned inside this block use the shims:
        subprocess.run(["uv", "run", "flubpub",
                        "--remote", f"root@host:{fr.prefix}-bj",
                        "list"], env=fr.env, check=True)
        fr.print_transcript()      # pretty dump
        entries = fr.read_transcript()  # structured access

The shims:
  - ssh:  recognizes `cd <dir> && uv run flubpub ...` and runs flubpub
          locally with FLUBPUB_DATA_DIR / FLUBPUB_SITE_DIR pointed at the
          fake install. Falls back to bash for unrecognized commands.
  - scp:  treats `host:path` as a local cp, rewriting the install prefix.

Verbose mode: pass `verbose=True` to FakeRemote (or set
FAKE_REMOTE_VERBOSE=1) to see one colored line per shim invocation on stderr.
"""
from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import stat
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class TranscriptEntry:
    ts: float
    op: str          # "ssh" | "scp"
    host: str
    rc: int
    duration_ms: float
    raw: dict        # the full JSON record


class FakeRemote:
    """Context manager that installs ssh/scp shims on PATH.

    Parameters:
      prefix:   path prefix the CLI will reference (default `/opt/flubpub`).
                Fake installs created via .install("key") live at
                `<actual>/flubpub-<key>` and are reachable through
                `--remote root@host:{prefix}-<key>`.
      verbose:  if True, shims print a one-line summary to stderr per call.
    """

    # Default stubs installed when stub_system_commands=True. Each is a
    # no-op shim that logs to the transcript. `uv` and `rsync` get their
    # own dedicated shims with side effects; everything below is pure log.
    DEFAULT_STUBS = ("systemctl", "nginx", "npm", "npx", "curl", "uv")

    def __init__(self, prefix: str = "/opt/flubpub", verbose: bool = False,
                 stub_system_commands: bool = False):
        self.prefix = prefix
        self.verbose = verbose or os.environ.get("FAKE_REMOTE_VERBOSE") == "1"
        self.stub_system_commands = stub_system_commands
        self._tmp: Path | None = None
        self._installs: dict[str, Path] = {}

    # ----- lifecycle -----

    def __enter__(self) -> "FakeRemote":
        self._tmp = Path(tempfile.mkdtemp(prefix="flubpub-fake-remote-"))
        (self._tmp / "bin").mkdir()
        (self._tmp / "inst").mkdir()
        self.transcript_path = self._tmp / "transcript.jsonl"
        self.transcript_path.touch()
        self.actual_prefix = self._tmp / "inst" / Path(self.prefix).name  # e.g. <tmp>/inst/flubpub
        self._write_shim("ssh", PROJECT_ROOT / "tests" / "_ssh_shim.py")
        self._write_shim("scp", PROJECT_ROOT / "tests" / "_scp_shim.py")
        self._write_shim("rsync", PROJECT_ROOT / "tests" / "_rsync_shim.py")
        if self.stub_system_commands:
            for name in self.DEFAULT_STUBS:
                self._write_shim(name, PROJECT_ROOT / "tests" / "_cmd_shim.py")
        return self

    def __exit__(self, *exc):
        if self._tmp and self._tmp.exists():
            shutil.rmtree(self._tmp)

    # ----- public surface -----

    @property
    def env(self) -> dict[str, str]:
        """Return an environment dict suitable for subprocess.run(env=...)."""
        return {
            **os.environ,
            "PATH": f"{self._tmp / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
            "FAKE_REMOTE_PREFIX": self.prefix,
            "FAKE_REMOTE_ACTUAL_PREFIX": str(self.actual_prefix),
            "FAKE_REMOTE_TRANSCRIPT": str(self.transcript_path),
            "FAKE_REMOTE_PROJECT_ROOT": str(PROJECT_ROOT),
            "FAKE_REMOTE_VERBOSE": "1" if self.verbose else "",
        }

    def install(self, key: str) -> Path:
        """Create a fake install directory with empty data/ and a minimal site/.

        Returns the on-disk path. The CLI will see this as `{prefix}-{key}`.
        """
        target = Path(f"{self.actual_prefix}-{key}")
        target.mkdir(parents=True, exist_ok=True)
        (target / "data").mkdir(exist_ok=True)
        # Minimal site skeleton — enough for flubpub list/get/delete; push
        # tests will need a richer copy.
        site = target / "site"
        site.mkdir(exist_ok=True)
        (site / "src").mkdir(exist_ok=True)
        (site / "src" / "pages").mkdir(exist_ok=True)
        (target / "data" / "pages.json").write_text("[]")
        self._installs[key] = target
        return target

    def install_with_real_site(self, key: str) -> Path:
        """Like install(), but copies the project's site/ skeleton so push/
        rebuild works end-to-end. Heavier; use only when needed."""
        target = self.install(key)
        repo_site = PROJECT_ROOT / "site"
        # Replace the empty site/ with a populated copy.
        shutil.rmtree(target / "site")
        shutil.copytree(repo_site, target / "site",
                        ignore=shutil.ignore_patterns("_site", "node_modules"))
        nm = repo_site / "node_modules"
        if nm.exists():
            (target / "site" / "node_modules").symlink_to(nm)
        return target

    def install_path(self, key: str) -> Path:
        return self._installs[key]

    def make_etc(self) -> Path:
        """Create a fake /etc tree with the directories deploy.sh writes into.
        Returned path is suitable for ETC=<path> when invoking deploy.sh."""
        assert self._tmp is not None
        etc = self._tmp / "etc"
        (etc / "systemd" / "system").mkdir(parents=True, exist_ok=True)
        (etc / "nginx" / "sites-available").mkdir(parents=True, exist_ok=True)
        (etc / "nginx" / "sites-enabled").mkdir(parents=True, exist_ok=True)
        return etc

    def remote_spec(self, key: str, host: str = "root@fake.invalid") -> str:
        """Return the `--remote` value that targets the named install."""
        return f"{host}:{self.prefix}-{key}"

    # ----- transcript -----

    def read_transcript(self) -> list[TranscriptEntry]:
        out: list[TranscriptEntry] = []
        for line in self.transcript_path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            out.append(TranscriptEntry(
                ts=r["ts"], op=r["op"], host=r["host"],
                rc=r["rc"], duration_ms=r["duration_ms"], raw=r,
            ))
        return out

    def print_transcript(self, file=sys.stderr) -> None:
        """Pretty-print the transcript, with paths relativized."""
        entries = self.read_transcript()
        if not entries:
            file.write("(transcript empty)\n")
            return
        t0 = entries[0].ts
        file.write(f"\n=== transcript ({len(entries)} call(s), prefix={self.prefix}) ===\n")
        op_color = {
            "ssh": "\033[36m", "scp": "\033[35m",
            "rsync": "\033[33m", "cmd": "\033[32m",
        }
        for i, e in enumerate(entries, 1):
            rel_t = e.ts - t0
            color = op_color.get(e.op, "")
            head = f"{color}{i:>2}. [{rel_t:5.2f}s] {e.op}→{e.host}\033[0m"
            tail = f"\033[2m({e.duration_ms}ms, rc={e.rc})\033[0m"
            file.write(f"  {head} {tail}\n")
            if e.op == "ssh":
                kind = e.raw.get("kind", "?")
                parsed = e.raw.get("parsed", {})
                if kind == "flubpub":
                    file.write(f"      remote_dir: {parsed.get('remote_dir')}\n")
                    file.write(f"      → actual:   {parsed.get('actual_dir')}\n")
                    file.write(f"      args:       {parsed.get('args')}\n")
                else:
                    cmd = parsed.get('translated', e.raw.get('remote_cmd', '')) or "(stdin heredoc)"
                    file.write(f"      cmd: {cmd[:120]}{'...' if len(cmd) > 120 else ''}\n")
            elif e.op == "scp":
                srcs = ", ".join(os.path.basename(s) for s in e.raw.get("srcs", []))
                file.write(f"      {srcs}  ({e.raw.get('bytes', 0)}B)\n")
                file.write(f"      → {e.raw.get('translated_dst')}\n")
            elif e.op == "rsync":
                trans = e.raw.get("translations", [])
                if trans:
                    for src, dst in trans:
                        file.write(f"      {src} → {dst}\n")
                else:
                    file.write(f"      argv: {' '.join(e.raw.get('argv', []))}\n")
            elif e.op == "cmd":
                file.write(f"      {e.raw.get('name', '?')} {' '.join(e.raw.get('args', []))}\n")
        file.write("=== end transcript ===\n")

    # ----- internals -----

    def _write_shim(self, name: str, source: Path) -> None:
        target = self._tmp / "bin" / name
        # Wrapper exports FAKE_CMD_NAME so the python shim can identify which
        # command it was invoked as (sys.argv[0] would just be the .py path).
        wrapper = textwrap.dedent(f"""\
            #!/usr/bin/env bash
            export FAKE_CMD_NAME={shlex.quote(name)}
            exec {shlex.quote(sys.executable)} {shlex.quote(str(source))} "$@"
        """)
        target.write_text(wrapper)
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
