"""Smoke test: `sync`'s content/<site>/ enumeration (_enumerate_content_site).

Run with: PYTHONUNBUFFERED=1 uv run python3 tests/smoke_test_sync_enumerate.py

Exercises the classifier directly (no FakeRemote): metadata entries whose name
starts with `.` or `_` are excluded silently, real flat/bundle pages are picked
up, the manifest index is resolved, and a genuinely malformed bundle (no leading
underscore, no entry file) still earns the skip warning.
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flubpub.cli import _enumerate_content_site


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    failures: list[str] = []

    site = Path(tempfile.mkdtemp(prefix="flubpub-enum-")) / "dwm"
    site.mkdir(parents=True)

    (site / "_manifest.toml").write_text('index = "home.md"\n')
    (site / "home.md").write_text("---\ntitle: Home\n---\n# Home\n")
    (site / "_pages.yaml").write_text("toy:\n  title: Toy\n")

    # real pages: a flat md, a flat html, and a bundle dir with an entry file
    (site / "essay.md").write_text("---\ntitle: Essay\n---\n# Essay\n")
    (site / "toy.html").write_text("<!doctype html><h1>Toy</h1>")
    bundle = site / "gallery"
    bundle.mkdir()
    (bundle / "gallery.html").write_text("<!doctype html><h1>Gallery</h1>")
    (bundle / "pic.png").write_bytes(b"\x89PNG")

    # metadata build dir: leading underscore, no entry file inside
    hub = site / "_hub"
    hub.mkdir()
    (hub / "build.py").write_text("# build script\n")
    (hub / "content.jsonl").write_text('{"type":"meta"}\n')

    # a genuinely malformed bundle: NOT underscore, NO entry file -> must warn
    broken = site / "oops"
    broken.mkdir()
    (broken / "stray.png").write_bytes(b"\x89PNG")

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(buf):
        index_entry, pages = _enumerate_content_site(site)
    out = buf.getvalue()

    if index_entry is None or index_entry.name != "home.md":
        failures.append(f"index not resolved to home.md: {index_entry!r}")

    if set(pages) != {"essay", "toy", "gallery"}:
        failures.append(f"unexpected page set: {sorted(pages)!r}")

    for meta_slug in ("_hub", "_manifest", "_pages", "home"):
        if meta_slug in pages:
            failures.append(f"metadata/index '{meta_slug}' leaked into pages")

    if "_hub" in out:
        failures.append(f"_hub triggered a skip warning (should be silent): {out!r}")

    if "oops" not in out or "no entry file" not in out:
        failures.append(f"malformed bundle 'oops' did not warn: {out!r}")

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All passed.")


if __name__ == "__main__":
    main()
