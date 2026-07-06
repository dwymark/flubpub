"""Smoke test: the `flubpub tunnel` CLI group (reverse SSH tunnel wrapper).

Run with: PYTHONUNBUFFERED=1 uv run python3 tests/smoke_test_tunnel.py

The tunnel group is a thin wrapper: `up`/`down` shell out to
deploy/tunnel/setup-tunnel.sh with derived env; `status`/`logs` shell out to
systemctl/journalctl. These tests exercise the real CLI as a subprocess (the
project's smoke-test convention) and assert the wrapper hands the right argv +
env to a stand-in for each downstream command, and propagates its exit code.

Cases:
  1. `up` passes explicit flags through as TUNNEL_PORT/REMOTE_HOST/REMOTE_USER/
     LOCAL_USER/LOCAL_SSH_PORT and propagates the script's exit code.
  2. `up` with no flags applies the documented defaults (port 47022,
     danielwymark.com, root, $USER, 22).
  3. `down` invokes the script with `--down` and only REMOTE_HOST/REMOTE_USER.
  4. `up`/`down` with a missing --script exit non-zero with a clear message.
  5. `status` invokes `systemctl --no-pager status flubpub-tunnel` and passes
     its (non-zero) rc straight through.
  6. `logs` invokes `journalctl -u flubpub-tunnel -n <lines>` (+ `-f` when
     --follow), honoring -n/--lines.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} {detail}")
        _failures.append(name)


def base_env() -> dict:
    """A clean env that still lets `uv run flubpub` work."""
    env = dict(os.environ)
    env.pop("LOCAL_USER", None)  # don't let an ambient value skew the default test
    return env


def run(args: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "flubpub", *args],
        cwd=REPO, env=env, capture_output=True, text=True,
    )


def make_recorder(dir_: Path, name: str, exit_code: int) -> Path:
    """A fake executable that records its argv + selected env to $TUNNEL_TEST_OUT."""
    p = dir_ / name
    p.write_text(
        "#!/usr/bin/env bash\n"
        "{\n"
        '  echo "ARGV=$*"\n'
        '  echo "TUNNEL_PORT=$TUNNEL_PORT"\n'
        '  echo "REMOTE_HOST=$REMOTE_HOST"\n'
        '  echo "REMOTE_USER=$REMOTE_USER"\n'
        '  echo "LOCAL_USER=$LOCAL_USER"\n'
        '  echo "LOCAL_SSH_PORT=$LOCAL_SSH_PORT"\n'
        '} > "$TUNNEL_TEST_OUT"\n'
        f"exit {exit_code}\n"
    )
    p.chmod(0o755)
    return p


def parse_out(out_path: Path) -> dict:
    d: dict[str, str] = {}
    for line in out_path.read_text().splitlines():
        k, _, v = line.partition("=")
        d[k] = v
    return d


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        out = tmp / "record.txt"

        # --- Case 1: up passes explicit flags through, propagates rc -----------
        script = make_recorder(tmp, "setup-tunnel.sh", exit_code=7)
        env = base_env()
        env["TUNNEL_TEST_OUT"] = str(out)
        proc = run(
            ["tunnel", "up", "--script", str(script),
             "--port", "5", "--remote-host", "h", "--remote-user", "u",
             "--local-user", "l", "--local-ssh-port", "9"],
            env,
        )
        check("up: rc propagates from script", proc.returncode == 7,
              f"(rc={proc.returncode}, stderr={proc.stderr!r})")
        rec = parse_out(out)
        check("up: explicit flags -> env",
              rec.get("TUNNEL_PORT") == "5" and rec.get("REMOTE_HOST") == "h"
              and rec.get("REMOTE_USER") == "u" and rec.get("LOCAL_USER") == "l"
              and rec.get("LOCAL_SSH_PORT") == "9",
              f"(rec={rec})")
        check("up: script called with no extra argv", rec.get("ARGV") == "",
              f"(ARGV={rec.get('ARGV')!r})")

        # --- Case 2: up defaults -----------------------------------------------
        out.unlink(missing_ok=True)
        env = base_env()
        env["TUNNEL_TEST_OUT"] = str(out)
        env["USER"] = "alice"
        proc = run(["tunnel", "up", "--script", str(script)], env)
        rec = parse_out(out)
        check("up: default port 47022", rec.get("TUNNEL_PORT") == "47022", f"(rec={rec})")
        check("up: default host danielwymark.com",
              rec.get("REMOTE_HOST") == "danielwymark.com", f"(rec={rec})")
        check("up: default user root", rec.get("REMOTE_USER") == "root", f"(rec={rec})")
        check("up: default local_user from $USER", rec.get("LOCAL_USER") == "alice",
              f"(rec={rec})")
        check("up: default local_ssh_port 22", rec.get("LOCAL_SSH_PORT") == "22",
              f"(rec={rec})")

        # --- Case 3: down invokes script with --down, only remote env ----------
        out.unlink(missing_ok=True)
        down_script = make_recorder(tmp, "setup-down.sh", exit_code=0)
        env = base_env()
        env["TUNNEL_TEST_OUT"] = str(out)
        proc = run(["tunnel", "down", "--script", str(down_script),
                    "--remote-host", "h", "--remote-user", "u"], env)
        check("down: rc propagates", proc.returncode == 0,
              f"(rc={proc.returncode}, stderr={proc.stderr!r})")
        rec = parse_out(out)
        check("down: script called with --down", rec.get("ARGV") == "--down",
              f"(ARGV={rec.get('ARGV')!r})")
        check("down: remote env set", rec.get("REMOTE_HOST") == "h"
              and rec.get("REMOTE_USER") == "u", f"(rec={rec})")
        check("down: no tunnel-port/local env leaked",
              rec.get("TUNNEL_PORT") == "" and rec.get("LOCAL_USER") == "",
              f"(rec={rec})")

        # --- Case 4: missing script errors cleanly -----------------------------
        env = base_env()
        proc = run(["tunnel", "up", "--script", "/no/such/file"], env)
        check("up: missing script -> non-zero", proc.returncode != 0,
              f"(rc={proc.returncode})")
        check("up: missing script -> clear message",
              "Tunnel script not found" in proc.stderr, f"(stderr={proc.stderr!r})")
        proc = run(["tunnel", "down", "--script", "/no/such/file"], env)
        check("down: missing script -> non-zero", proc.returncode != 0,
              f"(rc={proc.returncode})")

        # --- Case 5: status shells out to systemctl, passes rc through ---------
        shimdir = tmp / "bin"
        shimdir.mkdir()
        sysctl = shimdir / "systemctl"
        sysctl.write_text(
            '#!/usr/bin/env bash\necho "$*" > "$TUNNEL_TEST_OUT"\nexit 3\n'
        )
        sysctl.chmod(0o755)
        out.unlink(missing_ok=True)
        env = base_env()
        env["TUNNEL_TEST_OUT"] = str(out)
        env["PATH"] = f"{shimdir}{os.pathsep}{env['PATH']}"
        proc = run(["tunnel", "status"], env)
        check("status: rc propagates from systemctl", proc.returncode == 3,
              f"(rc={proc.returncode})")
        check("status: correct systemctl argv",
              out.read_text().strip() == "--no-pager status flubpub-tunnel",
              f"(argv={out.read_text().strip()!r})")

        # --- Case 6: logs shells out to journalctl -----------------------------
        journal = shimdir / "journalctl"
        journal.write_text(
            '#!/usr/bin/env bash\necho "$*" > "$TUNNEL_TEST_OUT"\nexit 0\n'
        )
        journal.chmod(0o755)
        out.unlink(missing_ok=True)
        env = base_env()
        env["TUNNEL_TEST_OUT"] = str(out)
        env["PATH"] = f"{shimdir}{os.pathsep}{env['PATH']}"
        run(["tunnel", "logs", "-n", "10"], env)
        check("logs: default argv with -n 10",
              out.read_text().strip() == "-u flubpub-tunnel -n 10",
              f"(argv={out.read_text().strip()!r})")
        out.unlink(missing_ok=True)
        run(["tunnel", "logs", "-f"], env)
        check("logs: -f appends follow, default -n 50",
              out.read_text().strip() == "-u flubpub-tunnel -n 50 -f",
              f"(argv={out.read_text().strip()!r})")

    if _failures:
        print(f"\n{len(_failures)} FAILURE(S): {_failures}")
        sys.exit(1)
    print("\nAll tunnel CLI smoke tests passed.")


if __name__ == "__main__":
    main()
