"""Smoke test: html-article metadata SSOT at content/<site>/_pages.yaml.

Run with: PYTHONUNBUFFERED=1 uv run python3 tests/smoke_test_pages_meta.py

The remote-side `uv run flubpub` is stubbed by FakeRemote; the mirror and the
_pages.yaml write run client-side after the (faked) remote push, so this checks
exactly that client-side bookkeeping. With a registry content_root configured:

  1. `--site dwm push <html> --description --tag` records the slug in _pages.yaml
  2. an `.md` push leaves _pages.yaml untouched (frontmatter is its SSOT)
  3. a content-only revise (no --description) preserves the stored description
  4. a revise with a new --description updates it
  5. delete prunes the slug from _pages.yaml
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.fakeremote import FakeRemote
import subprocess


def run(args: list[str], env: dict, expect_rc: int = 0) -> subprocess.CompletedProcess:
    proc = subprocess.run(["uv", "run", "flubpub", *args],
                          env=env, capture_output=True, text=True)
    if proc.returncode != expect_rc:
        sys.stderr.write(f"FAIL: {args} -> rc={proc.returncode} (expected {expect_rc})\n")
        sys.stderr.write(f"stdout: {proc.stdout}\nstderr: {proc.stderr}\n")
        sys.exit(1)
    return proc


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    failures: list[str] = []

    fake_home = Path(tempfile.mkdtemp(prefix="flubpub-fake-home-"))
    repo = Path(tempfile.mkdtemp(prefix="flubpub-fake-repo-"))
    (repo / "content" / "dwm").mkdir(parents=True, exist_ok=True)
    meta_path = repo / "content" / "dwm" / "_pages.yaml"

    def load_meta() -> dict:
        return yaml.safe_load(meta_path.read_text()) if meta_path.is_file() else {}

    with FakeRemote(verbose=True) as fr:
        fr.install("dwm")
        cfg_dir = fake_home / ".config" / "flubpub"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "sites.json").write_text(json.dumps({
            "default": "dwm",
            "content_root": str(repo),
            "sites": {"dwm": {"remote": f"root@fake.invalid:{fr.prefix}-dwm"}},
        }, indent=2))
        env = {**fr.env, "HOME": str(fake_home)}

        html = Path(tempfile.mkdtemp(prefix="flubpub-fake-src-")) / "toy.html"
        html.write_text("<!doctype html><h1>Toy</h1>")
        md = html.parent / "essay.md"
        md.write_text("---\ntitle: Essay\n---\n# Essay\n")

        print("\n--- case 1: html push records _pages.yaml ---")
        run(["--site", "dwm", "push", str(html), "--title", "Toy",
             "--description", "<span>a toy</span>", "--tag", "draft"], env)
        m = load_meta()
        if "toy" not in m:
            failures.append(f"case1: 'toy' missing from _pages.yaml: {m!r}")
        elif m["toy"].get("description") != "<span>a toy</span>" or m["toy"].get("tags") != ["draft"]:
            failures.append(f"case1: wrong stored fields: {m.get('toy')!r}")

        print("\n--- case 2: md push leaves _pages.yaml untouched ---")
        run(["--site", "dwm", "push", str(md), "--title", "Essay",
             "--description", "<span>an essay</span>"], env)
        if "essay" in load_meta():
            failures.append("case2: md slug 'essay' leaked into _pages.yaml")

        print("\n--- case 3: content-only revise preserves description ---")
        run(["--site", "dwm", "revise", "toy", str(html)], env)
        if load_meta().get("toy", {}).get("description") != "<span>a toy</span>":
            failures.append(f"case3: description not preserved: {load_meta().get('toy')!r}")

        print("\n--- case 4: revise with new description updates it ---")
        run(["--site", "dwm", "revise", "toy", str(html),
             "--description", "<span>a better toy</span>"], env)
        if load_meta().get("toy", {}).get("description") != "<span>a better toy</span>":
            failures.append(f"case4: description not updated: {load_meta().get('toy')!r}")

        print("\n--- case 5: delete prunes the slug ---")
        run(["--site", "dwm", "delete", "toy"], env)
        if "toy" in load_meta():
            failures.append("case5: 'toy' not pruned from _pages.yaml after delete")

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All passed.")


if __name__ == "__main__":
    main()
