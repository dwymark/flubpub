#!/usr/bin/env python3
"""Stand-in for rsync. Translates `host:path` arguments via the install-prefix
rewrite, then execs real rsync against the rewritten paths so all the flag
semantics (--exclude, -a, etc.) behave correctly."""
import json
import os
import shutil
import subprocess
import sys
import time

PREFIX = os.environ["FAKE_REMOTE_PREFIX"]
ACTUAL = os.environ["FAKE_REMOTE_ACTUAL_PREFIX"]
TRANSCRIPT = os.environ["FAKE_REMOTE_TRANSCRIPT"]
VERBOSE = os.environ.get("FAKE_REMOTE_VERBOSE") == "1"

translations: list[tuple[str, str]] = []
new_argv = []
for a in sys.argv[1:]:
    # Match host:path (host may contain @, path must start with / for our use)
    if ":" in a and not a.startswith("-"):
        host, _, path = a.partition(":")
        if path.startswith(PREFIX):
            new_path = path.replace(PREFIX, ACTUAL)
            translations.append((a, new_path))
            new_argv.append(new_path)
            continue
    new_argv.append(a)

t0 = time.monotonic()
# Find the REAL rsync at known system paths. Cannot use shutil.which()
# without filtering: our own shim is first on PATH and would recurse.
real = next(
    (p for p in ("/usr/bin/rsync", "/bin/rsync", "/usr/local/bin/rsync")
     if os.path.exists(p)),
    "/usr/bin/rsync",
)
proc = subprocess.run(
    [real, *new_argv],
    stdin=subprocess.DEVNULL, capture_output=True, text=True,
)
dt_ms = round((time.monotonic() - t0) * 1000, 1)

entry = {
    "ts": time.time(),
    "op": "rsync",
    "argv": sys.argv[1:],
    "translations": translations,
    "rc": proc.returncode,
    "duration_ms": dt_ms,
    "stdout_len": len(proc.stdout),
    "stderr_len": len(proc.stderr),
    "host": "<rsync>",
}
with open(TRANSCRIPT, "a") as f:
    f.write(json.dumps(entry) + "\n")

if VERBOSE:
    summary = ", ".join(f"{a}→{b}" for a, b in translations) or "(no translation)"
    sys.stderr.write(
        f"\033[33m[rsync]\033[0m \033[2m({dt_ms}ms, rc={proc.returncode})\033[0m {summary}\n"
    )

sys.stdout.write(proc.stdout)
sys.stderr.write(proc.stderr)
sys.exit(proc.returncode)
