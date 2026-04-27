#!/usr/bin/env python3
"""Stand-in for ssh. Logs the call, rewrites a path prefix, and either
locally-executes the recognized `cd <dir> && uv run flubpub <args>` pattern
or bash-evals the rewritten command.

Driven by env vars set by tests.fakeremote.FakeRemote:
  FAKE_REMOTE_PREFIX         e.g. "/opt/flubpub"
  FAKE_REMOTE_ACTUAL_PREFIX  e.g. "<tmp>/inst/flubpub"
  FAKE_REMOTE_TRANSCRIPT     append-only JSONL log path
  FAKE_REMOTE_PROJECT_ROOT   where to run `uv run flubpub` from
  FAKE_REMOTE_VERBOSE        if "1", echo a one-line summary to stderr
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time

PREFIX = os.environ["FAKE_REMOTE_PREFIX"]
ACTUAL = os.environ["FAKE_REMOTE_ACTUAL_PREFIX"]
TRANSCRIPT = os.environ["FAKE_REMOTE_TRANSCRIPT"]
PROJECT_ROOT = os.environ["FAKE_REMOTE_PROJECT_ROOT"]
VERBOSE = os.environ.get("FAKE_REMOTE_VERBOSE") == "1"

# Strip ssh option flags (-o, -i, -p ...) — flubpub doesn't pass them but
# operators sometimes will, and a real shim should be tolerant.
positional = []
i = 1
argv = sys.argv
while i < len(argv):
    a = argv[i]
    if a in ("-o", "-i", "-p", "-l", "-F"):
        i += 2
        continue
    if a.startswith("-"):
        i += 1
        continue
    positional.append(a)
    i += 1

host = positional[0] if positional else "<missing-host>"
remote_cmd = " ".join(positional[1:])

translated = remote_cmd.replace(PREFIX, ACTUAL)

# Recognize the canonical flubpub invocation so we can execute it through
# the project's installed package without needing a real install on disk.
PATTERN = re.compile(
    r'^PATH="\$HOME/\.local/bin:\$PATH"\s*&&\s*cd\s+(\S+)\s*&&\s*uv\s+run\s+flubpub\s+(.*)$'
)
m = PATTERN.match(remote_cmd)

# Optional richer execution mode. Default is to STUB the flubpub call —
# we record the parsed remote_dir/args and exit success. This is enough
# to verify the CLI's --remote routing without standing up a server on
# every fake install. Tests that need real round-trip can set
# FAKE_REMOTE_EXECUTE=1 (TODO: plumb a server-per-install for this).
EXECUTE = os.environ.get("FAKE_REMOTE_EXECUTE") == "1"

t0 = time.monotonic()


class _Stub:
    def __init__(self, stdout: str = "", stderr: str = "", rc: int = 0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, rc


if m:
    raw_dir = m.group(1)
    remote_dir = shlex.split(raw_dir)[0] if raw_dir else raw_dir
    args_str = m.group(2)
    actual_dir = remote_dir.replace(PREFIX, ACTUAL)
    parsed_kind = "flubpub"
    parsed = {"remote_dir": remote_dir, "actual_dir": actual_dir, "args": args_str}
    if EXECUTE:
        env = {
            **os.environ,
            "FLUBPUB_DATA_DIR": f"{actual_dir}/data",
            "FLUBPUB_SITE_DIR": f"{actual_dir}/site",
        }
        proc = subprocess.run(
            ["uv", "run", "flubpub", *shlex.split(args_str)],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True,
        )
    else:
        proc = _Stub(stdout=f"[fake-flubpub] dir={actual_dir} args={args_str}\n")
else:
    proc = subprocess.run(["bash", "-c", translated], capture_output=True, text=True)
    parsed_kind = "bash"
    parsed = {"translated": translated}

dt_ms = round((time.monotonic() - t0) * 1000, 1)

entry = {
    "ts": time.time(),
    "op": "ssh",
    "host": host,
    "remote_cmd": remote_cmd,
    "kind": parsed_kind,
    "parsed": parsed,
    "rc": proc.returncode,
    "duration_ms": dt_ms,
    "stdout_len": len(proc.stdout),
    "stderr_len": len(proc.stderr),
}
with open(TRANSCRIPT, "a") as f:
    f.write(json.dumps(entry) + "\n")

if VERBOSE:
    sys.stderr.write(
        f"\033[36m[ssh→{host}]\033[0m {parsed_kind} "
        f"\033[2m({dt_ms}ms, rc={proc.returncode})\033[0m "
        f"{parsed.get('args') or parsed.get('translated', '')}\n"
    )

sys.stdout.write(proc.stdout)
sys.stderr.write(proc.stderr)
sys.exit(proc.returncode)
