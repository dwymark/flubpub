"""Smoke test for the "papered" theme family.

Renders the canonical sample through every papered theme and asserts:
1. Each theme template loads without Jinja2 errors.
2. The output contains the page-level color-scheme injection (so the
   Jinja2 inheritance chain produced a complete document).
3. The output contains the inline wallpaper SVG marker.
4. Each theme/scheme pair declares the custom-property contract the
   shared base template depends on.
5. available_themes() lists all ten papered themes (verifying the
   subdirectory base template is hidden).

Run with:
    uv run python3 tests/smoke_test_papered_themes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from the repo root without an install step.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from flubpub.colors import COLOR_SCHEMES, DEFAULT_SCHEMES
from flubpub.server import available_themes, render_themed_page

PAPERED = [
    "folio", "alpine", "harbor", "engineroom", "kiln",
    "latticework", "meadow", "ember", "quarry", "nocturne",
]

# The shared base template reads these properties; every papered scheme
# must define them or the cards/wallpapers will fall back to UA defaults.
REQUIRED_VARS = {
    "--bg", "--fg", "--heading", "--accent", "--link", "--link-visited",
    "--rule", "--code-bg", "--code-fg",
    "--card-bg", "--ink-light", "--pattern-fg", "--pattern-accent",
}


def test_base_template_hidden() -> None:
    themes = set(available_themes())
    assert "_base" not in themes, "base template leaked into available_themes()"
    for t in PAPERED:
        assert t in themes, f"papered theme {t!r} missing from available_themes()"
    print(f"  available_themes() lists all {len(PAPERED)} papered themes; base is hidden.")


def test_default_schemes_complete() -> None:
    for t in PAPERED:
        assert DEFAULT_SCHEMES.get(t) == t, (
            f"theme {t!r} should default to scheme {t!r}, got {DEFAULT_SCHEMES.get(t)!r}"
        )
    print(f"  DEFAULT_SCHEMES maps each papered theme -> its eponymous scheme.")


def test_schemes_carry_required_contract() -> None:
    for t in PAPERED:
        scheme = COLOR_SCHEMES[t]
        missing = REQUIRED_VARS - set(scheme.keys())
        assert not missing, f"scheme {t!r} missing required vars: {sorted(missing)}"
    print(f"  All {len(PAPERED)} schemes define the required custom-property contract.")


def test_themes_render_without_errors() -> None:
    sample = '<div class="markdown-content"><h1>Test</h1><p>Hello.</p></div>'
    for t in PAPERED:
        out = render_themed_page(
            theme=t, slug="t", title="Test", content=sample,
            date="2026-05-10", color_scheme=None,
        )
        assert "<!DOCTYPE html>" in out, f"theme {t!r}: no doctype in output"
        assert ":root {" in out, f"theme {t!r}: color-scheme :root block missing"
        assert "--pattern-fg" in out, f"theme {t!r}: pattern-fg not injected"
        assert 'class="wallpaper"' in out, f"theme {t!r}: wallpaper layer missing"
        assert "<svg" in out, f"theme {t!r}: no inline svg in wallpaper layer"
        assert "url(#papered-" in out, f"theme {t!r}: pattern fill URL missing"
        assert "Hello." in out, f"theme {t!r}: content not interpolated"
    print(f"  All {len(PAPERED)} themes render with the expected scaffolding.")


def main() -> None:
    test_base_template_hidden()
    test_default_schemes_complete()
    test_schemes_carry_required_contract()
    test_themes_render_without_errors()
    print("\nOK: papered theme family smoke test passed.")


if __name__ == "__main__":
    main()
