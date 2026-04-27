#!/usr/bin/env python3
"""Generic command stub. Logs the call to the transcript and exits 0.

A handful of commands need a tiny side effect to keep deploy.sh making
forward progress; those are switched on by argv[0] basename:

  uv:    `uv build` writes a fake wheel into ./dist/
         `uv venv <dir>` creates <dir>
         all other invocations are no-ops.

Everything else (systemctl, nginx, npm, npx, curl) is a pure no-op.
"""
import json
import os
import sys
import time
from pathlib import Path

TRANSCRIPT = os.environ["FAKE_REMOTE_TRANSCRIPT"]
VERBOSE = os.environ.get("FAKE_REMOTE_VERBOSE") == "1"

name = os.environ.get("FAKE_CMD_NAME") or Path(sys.argv[0]).name
args = sys.argv[1:]

# A few commands need a tiny effect to let deploy.sh proceed.
if name == "uv":
    if args[:1] == ["build"]:
        Path("dist").mkdir(exist_ok=True)
        Path("dist/flubpub-fake-0.0.0-py3-none-any.whl").write_bytes(b"FAKE")
    elif args[:1] == ["venv"] and len(args) >= 2:
        venv_dir = Path(args[1])
        venv_dir.mkdir(parents=True, exist_ok=True)
        # Touch a fake uvicorn so ExecStart can resolve in postmortem inspection.
        (venv_dir / "bin").mkdir(exist_ok=True)
        (venv_dir / "bin" / "uvicorn").write_text("#!/usr/bin/env true\n")
        (venv_dir / "bin" / "uvicorn").chmod(0o755)

entry = {
    "ts": time.time(),
    "op": "cmd",
    "name": name,
    "args": args,
    "rc": 0,
    "duration_ms": 0.0,
    "host": "<local>",
}
with open(TRANSCRIPT, "a") as f:
    f.write(json.dumps(entry) + "\n")

if VERBOSE:
    sys.stderr.write(
        f"\033[32m[{name}]\033[0m {' '.join(args)}\n"
    )

sys.exit(0)
