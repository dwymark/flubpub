#!/usr/bin/env python3
"""Stand-in for scp. Treats `host:path` as a local copy and rewrites the
path prefix the same way the ssh shim does.

flubpub's CLI calls scp with paths like `<host>:/tmp/flubpub-upload-foo`,
which don't begin with the install prefix; those are copied to /tmp directly,
which is fine because /tmp is shared with the "remote".
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

PREFIX = os.environ["FAKE_REMOTE_PREFIX"]
ACTUAL = os.environ["FAKE_REMOTE_ACTUAL_PREFIX"]
TRANSCRIPT = os.environ["FAKE_REMOTE_TRANSCRIPT"]
VERBOSE = os.environ.get("FAKE_REMOTE_VERBOSE") == "1"

# Strip scp flags (-r, -P, -i, -o ...).
args = []
i = 1
argv = sys.argv
while i < len(argv):
    a = argv[i]
    if a in ("-P", "-i", "-o", "-l", "-F"):
        i += 2
        continue
    if a.startswith("-"):
        i += 1
        continue
    args.append(a)
    i += 1

if len(args) < 2:
    sys.stderr.write(f"fake scp: need >=2 positional args, got {args}\n")
    sys.exit(64)

dst_spec = args[-1]
srcs = args[:-1]

# host:path → split on the FIRST colon (path may contain colons later).
if ":" in dst_spec:
    host, _, dst_path = dst_spec.partition(":")
else:
    host, dst_path = "<local>", dst_spec

translated_dst = dst_path.replace(PREFIX, ACTUAL) if dst_path.startswith(PREFIX) else dst_path

t0 = time.monotonic()
total_bytes = 0
try:
    for src in srcs:
        total_bytes += os.path.getsize(src)
        # If multiple srcs, dst must be a directory. flubpub only ever sends
        # one src at a time, so a plain copy is fine.
        if len(srcs) == 1:
            shutil.copy(src, translated_dst)
        else:
            os.makedirs(translated_dst, exist_ok=True)
            shutil.copy(src, os.path.join(translated_dst, os.path.basename(src)))
    rc = 0
    err = ""
except Exception as e:
    rc = 1
    err = str(e)

dt_ms = round((time.monotonic() - t0) * 1000, 1)

entry = {
    "ts": time.time(),
    "op": "scp",
    "host": host,
    "srcs": srcs,
    "dst": dst_path,
    "translated_dst": translated_dst,
    "bytes": total_bytes,
    "rc": rc,
    "duration_ms": dt_ms,
    "error": err,
}
with open(TRANSCRIPT, "a") as f:
    f.write(json.dumps(entry) + "\n")

if VERBOSE:
    sys.stderr.write(
        f"\033[35m[scp→{host}]\033[0m "
        f"\033[2m({total_bytes}B, {dt_ms}ms, rc={rc})\033[0m "
        f"{' '.join(os.path.basename(s) for s in srcs)} → {translated_dst}\n"
    )

if err:
    sys.stderr.write(f"fake scp: {err}\n")
sys.exit(rc)
