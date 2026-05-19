"""Smoke test: automatic content/ mirror-on-write.

Run with: PYTHONUNBUFFERED=1 uv run python3 tests/smoke_test_mirror.py

Every push/revise/set-index/delete that resolves to a registry site key
copies the published bundle into content/<key>/ so the tree stays the
canonical SSOT without manual upkeep. This exercises the client-side
mirror (the remote-side flubpub is stubbed by the ssh shim, rc=0).

The CLI is invoked via the built venv console script with cwd pointed at
an isolated fake repo (a bare .git marker), so _content_root() resolves
there and the test never touches the real content/ tree.

Cases:
  1. Flat file (no refs)         → content/dwm/<slug>.<ext>
  2. Bundle (md + image)         → content/dwm/<slug>/ directory
  3. revise                      → mirrored copy updated in place
  4. delete                      → mirrored copy removed
  5. --no-mirror                 → nothing written
  6. FLUBPUB_NO_MIRROR=1         → nothing written
  7. --local                     → not registry-backed, no mirror
  8. shape reconcile flat→dir    → stale flat file dropped
  9. in-place re-publish        → no SameFileError crash, bundle intact
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

    fake_home = Path(tempfile.mkdtemp(prefix="flubpub-mirror-home-"))
    fake_repo = Path(tempfile.mkdtemp(prefix="flubpub-mirror-repo-"))
    (fake_repo / ".git").mkdir()  # _content_root() marker
    src = Path(tempfile.mkdtemp(prefix="flubpub-mirror-src-"))
    content_dwm = fake_repo / "content" / "dwm"

    with FakeRemote(verbose=False) as fr:
        fr.install("dwm")
        cfg = fake_home / ".config" / "flubpub"
        cfg.mkdir(parents=True)
        (cfg / "sites.json").write_text(json.dumps({
            "default": "dwm",
            "sites": {"dwm": {"remote": fr.remote_spec("dwm")}},
        }, indent=2))

        def flub(args: list[str], extra_env: dict | None = None,
                 expect_rc: int = 0) -> subprocess.CompletedProcess:
            env = {**fr.env, "HOME": str(fake_home)}
            if extra_env:
                env.update(extra_env)
            proc = subprocess.run(
                [str(FLUBPUB), *args], cwd=str(fake_repo),
                env=env, capture_output=True, text=True,
            )
            if expect_rc is not None and proc.returncode != expect_rc:
                sys.stderr.write(
                    f"FAIL: {args} rc={proc.returncode} (want {expect_rc})\n"
                    f"stdout: {proc.stdout}\nstderr: {proc.stderr}\n"
                )
                sys.exit(1)
            return proc

        # Sources carry their slug in frontmatter (the CLI reads it), so no
        # explicit --slug override is passed. That keeps this test focused on
        # the content/ mirror: with no CLI override the in-file-SoT writeback
        # (#11) is a no-op, so the mirrored file equals the source verbatim.

        # --- case 1: flat file, no refs ---
        print("--- case 1: flat mirror ---")
        ALPHA = "---\nslug: alpha\n---\n# Alpha\n\nplain body\n"
        (src / "alpha.md").write_text(ALPHA)
        flub(["--site", "dwm", "push", str(src / "alpha.md")])
        flat = content_dwm / "alpha.md"
        check(flat.is_file(), "case1: content/dwm/alpha.md not created")
        check(flat.read_text() == ALPHA, "case1: flat content mismatch")

        # --- case 2: bundle (md + referenced image) → directory shape ---
        print("--- case 2: bundle mirror ---")
        bdir = src / "beta-src"
        bdir.mkdir()
        (bdir / "page.md").write_text("---\nslug: beta\n---\n# Beta\n\n![pic](pic.png)\n")
        (bdir / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n_fake_")
        flub(["--site", "dwm", "push", str(bdir / "page.md")])
        check((content_dwm / "beta" / "page.md").is_file(),
              "case2: content/dwm/beta/page.md missing")
        check((content_dwm / "beta" / "pic.png").read_bytes()
              == b"\x89PNG\r\n\x1a\n_fake_",
              "case2: bundled asset missing/mismatch")
        check(not (content_dwm / "beta.md").exists(),
              "case2: unexpected flat beta.md alongside dir shape")

        # --- case 3: revise updates the mirrored copy ---
        print("--- case 3: revise re-mirrors ---")
        ALPHA2 = "---\nslug: alpha\n---\n# Alpha\n\nrevised body\n"
        (src / "alpha2.md").write_text(ALPHA2)
        flub(["--site", "dwm", "revise", "alpha", str(src / "alpha2.md")])
        check(flat.read_text() == ALPHA2,
              "case3: revise did not update mirror")

        # --- case 4: delete removes the mirrored copy ---
        print("--- case 4: delete unmirrors ---")
        flub(["--site", "dwm", "delete", "alpha"])
        check(not flat.exists(), "case4: content/dwm/alpha.md not removed")
        check((content_dwm / "beta" / "page.md").is_file(),
              "case4: delete should not touch other slugs")

        # --- case 5: --no-mirror skips ---
        print("--- case 5: --no-mirror ---")
        (src / "gamma.md").write_text("---\nslug: gamma\n---\n# Gamma\n")
        flub(["--no-mirror", "--site", "dwm", "push", str(src / "gamma.md")])
        check(not (content_dwm / "gamma.md").exists(),
              "case5: --no-mirror still wrote content/dwm/gamma.md")

        # --- case 6: FLUBPUB_NO_MIRROR=1 skips ---
        print("--- case 6: FLUBPUB_NO_MIRROR env ---")
        (src / "delta.md").write_text("---\nslug: delta\n---\n# Delta\n")
        flub(["--site", "dwm", "push", str(src / "delta.md")],
             extra_env={"FLUBPUB_NO_MIRROR": "1"})
        check(not (content_dwm / "delta.md").exists(),
              "case6: FLUBPUB_NO_MIRROR still wrote content/dwm/delta.md")

        # --- case 7: --local is not registry-backed → no mirror ---
        print("--- case 7: --local skips ---")
        (src / "epsilon.md").write_text("---\nslug: epsilon\n---\n# Epsilon\n")
        # No local server running → push fails, but the point is that no
        # content/ copy is produced regardless of outcome.
        flub(["--local", "push", str(src / "epsilon.md")],
             expect_rc=None)
        check(not (content_dwm / "epsilon.md").exists(),
              "case7: --local push wrote content/dwm/epsilon.md")

        # --- case 8: shape reconcile flat → dir ---
        print("--- case 8: flat→dir reconcile ---")
        (src / "zeta.md").write_text("---\nslug: zeta\n---\n# Zeta\n\nno refs\n")
        flub(["--site", "dwm", "push", str(src / "zeta.md")])
        check((content_dwm / "zeta.md").is_file(), "case8: flat zeta.md missing")
        zdir = src / "zeta-src"
        zdir.mkdir()
        (zdir / "zeta.md").write_text("---\nslug: zeta\n---\n# Zeta\n\n![p](p.png)\n")
        (zdir / "p.png").write_bytes(b"_png_")
        flub(["--site", "dwm", "push", str(zdir / "zeta.md")])
        check(not (content_dwm / "zeta.md").exists(),
              "case8: stale flat zeta.md not reconciled away")
        check((content_dwm / "zeta" / "zeta.md").is_file(),
              "case8: dir-shape zeta/zeta.md missing")

        # --- case 9: re-publishing the canonical content/ file in place
        # must not crash (SameFileError) or corrupt/drop the bundle ---
        print("--- case 9: in-place re-publish ---")
        flub(["--site", "dwm", "push",
              str(content_dwm / "beta" / "page.md")])
        check((content_dwm / "beta" / "page.md").read_text()
              == "---\nslug: beta\n---\n# Beta\n\n![pic](pic.png)\n",
              "case9: in-place re-publish corrupted the entry")
        check((content_dwm / "beta" / "pic.png").is_file(),
              "case9: in-place re-publish dropped a bundled asset")

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All passed.")


if __name__ == "__main__":
    main()
