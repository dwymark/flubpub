"""Smoke test for deploy/deploy.sh: site parameterization, idempotence, and
that two side-by-side deploys produce two distinct, non-conflicting installs.

Run with: PYTHONUNBUFFERED=1 uv run python3 tests/smoke_test_deploy.py

The harness shims ssh, scp, rsync, plus the "system" commands deploy.sh
invokes on the remote (systemctl, nginx, npm, npx, uv, curl). The remote
side runs locally in bash via the ssh shim, with our fake /etc tree
substituted for the real one (ETC=...).

Asserts that, after deploying sites 'dwm' (port 8001, host danielwymark.com)
and 'bj' (port 8002, host bijectivity.net):

  1. /etc/systemd/system/flubpub@.service exists with the templated body.
  2. /etc/nginx/sites-available/flubpub-dwm and -bj exist with correct
     SERVER_NAME, INSTALL_ROOT, PORT substitutions.
  3. /etc/nginx/sites-enabled/* are symlinks to the available files.
  4. Each install has a populated instance.env with the right port.
  5. systemctl was called with the right instance names.
  6. The two installs do not collide on disk or in nginx config.
  7. Re-running deploy.sh for an existing site is idempotent (no error).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.fakeremote import FakeRemote


def run_deploy(site: str, server_name: str, port: str, fr: FakeRemote, etc: Path,
               cwd: Path) -> subprocess.CompletedProcess:
    env = {
        **fr.env,
        "SITE": site,
        "REMOTE_HOST": "fake.invalid",
        "SERVER_NAME": server_name,
        "PORT": port,
        "ETC": str(etc),
    }
    # Stream output live so a hang is diagnosable. stdin=DEVNULL prevents
    # the inner bash heredoc from getting confused by an inherited terminal.
    proc = subprocess.run(
        ["bash", str(Path.cwd() / "deploy" / "deploy.sh")],
        env=env, cwd=cwd, stdin=subprocess.DEVNULL,
    )
    return proc


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    failures: list[str] = []
    project_root = Path.cwd()

    with FakeRemote(verbose=True, stub_system_commands=True) as fr:
        etc = fr.make_etc()

        print("\n--- deploying site 'dwm' ---")
        proc = run_deploy("dwm", "danielwymark.com", "8001", fr, etc,
                          cwd=project_root)
        if proc.returncode != 0:
            failures.append(f"dwm deploy rc={proc.returncode}")

        print("\n--- deploying site 'bj' ---")
        proc = run_deploy("bj", "bijectivity.net", "8002", fr, etc,
                          cwd=project_root)
        if proc.returncode != 0:
            failures.append(f"bj deploy rc={proc.returncode}")

        print("\n--- checking artifacts ---")

        unit = etc / "systemd" / "system" / "flubpub@.service"
        if not unit.is_file():
            failures.append(f"templated unit missing: {unit}")
        else:
            body = unit.read_text()
            for needle in ("Description=flubpub web server (%i)",
                           "WorkingDirectory=/opt/flubpub-%i",
                           "EnvironmentFile=/opt/flubpub-%i/instance.env",
                           "${FLUBPUB_PORT}"):
                if needle not in body:
                    failures.append(f"unit missing '{needle}'")

        # In the harness, deploy.sh's heredoc body had its install-prefix
        # rewritten by the ssh shim, so on-disk paths reflect the temp tree.
        # Production paths (`/opt/flubpub-<site>`) are verified via the
        # transcript instead — see further down.
        for site, server_name, port in [
            ("dwm", "danielwymark.com", "8001"),
            ("bj",  "bijectivity.net",  "8002"),
        ]:
            avail = etc / "nginx" / "sites-available" / f"flubpub-{site}"
            enabled = etc / "nginx" / "sites-enabled" / f"flubpub-{site}"
            install = Path(f"{fr.actual_prefix}-{site}")
            if not avail.is_file():
                failures.append(f"nginx site missing: {avail}")
                continue
            body = avail.read_text()
            for needle in (f"server_name {server_name};",
                           f"root {install}/site/_site;",
                           f"proxy_pass http://127.0.0.1:{port};"):
                if needle not in body:
                    failures.append(f"{site}: nginx body missing '{needle}'")
            if "__SERVER_NAME__" in body or "__INSTALL_ROOT__" in body or "__PORT__" in body:
                failures.append(f"{site}: nginx body has unsubstituted placeholder")
            if not enabled.is_symlink():
                failures.append(f"{site}: enabled is not a symlink: {enabled}")
            elif os.readlink(enabled) != str(avail):
                failures.append(f"{site}: enabled points to {os.readlink(enabled)}, "
                                f"expected {avail}")

            env_file = install / "instance.env"
            if not env_file.is_file():
                failures.append(f"{site}: instance.env missing at {env_file}")
            else:
                env_body = env_file.read_text()
                for needle in (f"FLUBPUB_DATA_DIR={install}/data",
                               f"FLUBPUB_SITE_DIR={install}/site",
                               f"FLUBPUB_PORT={port}"):
                    if needle not in env_body:
                        failures.append(f"{site}: instance.env missing '{needle}'")

        # 4b. Verify the heredoc that was sent to ssh (pre-translation) has
        # PRODUCTION paths. If this test passed but those strings were absent,
        # we'd be testing a fiction.
        bash_ssh_entries = [
            e for e in fr.read_transcript()
            if e.op == "ssh" and e.raw.get("kind") == "bash"
            and e.raw.get("parsed", {}).get("stdin_bytes", 0) > 0
        ]
        if not bash_ssh_entries:
            failures.append("no bash heredoc captured in transcript")
        for site in ("dwm", "bj"):
            heredoc_for_site = next(
                (e.raw["parsed"]["stdin_pre"] for e in bash_ssh_entries
                 if f"flubpub@{site}" in e.raw["parsed"].get("stdin_pre", "")),
                None,
            )
            if heredoc_for_site is None:
                failures.append(f"no heredoc captured for site {site}")
                continue
            for needle in (f"FLUBPUB_DATA_DIR=/opt/flubpub-{site}/data",
                           f"FLUBPUB_SITE_DIR=/opt/flubpub-{site}/site",
                           f"systemctl restart \"flubpub@{site}\""):
                if needle not in heredoc_for_site:
                    failures.append(f"{site}: production heredoc missing '{needle}'")

        # 5. systemctl called with right instances.
        sysctl_calls = [
            e for e in fr.read_transcript()
            if e.op == "cmd" and e.raw.get("name") == "systemctl"
        ]
        joined = " | ".join(" ".join(e.raw["args"]) for e in sysctl_calls)
        for needle in ("enable flubpub@dwm", "restart flubpub@dwm",
                       "enable flubpub@bj", "restart flubpub@bj",
                       "reload nginx"):
            if needle not in joined:
                failures.append(f"systemctl never called: '{needle}'")

        # 6. Cross-site isolation: dwm's nginx config does not mention bj
        dwm_body = (etc / "nginx" / "sites-available" / "flubpub-dwm").read_text()
        if "bj" in dwm_body or "bijectivity" in dwm_body:
            failures.append("dwm nginx body leaked bj references")
        bj_body = (etc / "nginx" / "sites-available" / "flubpub-bj").read_text()
        if "dwm" in bj_body or "danielwymark" in bj_body:
            failures.append("bj nginx body leaked dwm references")

        # 7. Idempotence: re-deploy dwm.
        print("\n--- re-deploying 'dwm' (idempotence check) ---")
        proc = run_deploy("dwm", "danielwymark.com", "8001", fr, etc,
                          cwd=project_root)
        if proc.returncode != 0:
            failures.append(f"dwm re-deploy rc={proc.returncode}")

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
