#!/usr/bin/env python3
"""Extract the frontmatter description: string of every dwm .md article that
carries one, split into byline (.ai-work) and blurb, and emit the palm-eink
illuminated batch-edit form. Paste-back ingested by apply_edits.py.

Usage: python3 build_description_form.py [OUT_HTML]   (default: <repo>/scratch/description-edit-form.html)

Note: html-bundle articles keep their listing description in production
pages.json, not in content/, so they are out of scope here.
"""
import re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import formkit as fk

try:
    import yaml
except ModuleNotFoundError:
    sys.exit("needs pyyaml: run via `uv run --with pyyaml python3 build_description_form.py`")


def grab(cls, desc):
    m = re.search(r'<span class="%s"[^>]*title="(.*?)"[^>]*>(.*?)</span>' % cls, desc, re.S)
    return (m.group(1).strip(), fk.decode(m.group(2))) if m else (None, None)


def extract(content_dir):
    cards = []
    for p in sorted(content_dir.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---", text, re.S)
        if not m:
            continue
        fm = yaml.safe_load(m.group(1)) or {}
        desc = fm.get("description")
        if not desc:
            continue
        _bt, byline = grab("ai-work", desc)
        _dt, note = grab("ai-desc", desc)
        blurb = re.sub(r'<span class="ai-(work|desc)"[^>]*>.*?</span>', "", desc, flags=re.S)
        blurb = fk.decode(blurb)
        key = p.name
        fields = [
            {"id": "%s :: byline" % key, "label": "byline (.ai-work)", "value": byline or "", "multiline": False},
            {"id": "%s :: blurb" % key, "label": "blurb", "value": blurb, "multiline": True},
        ]
        cards.append({
            "key": key,
            "title": fm.get("title", p.stem),
            "fields": fields,
            "foot": ("preserved note: " + note) if note else "",
        })
    return cards


SUB = ('The frontmatter <code>description:</code> of every dwm article that carries one, '
       'split into <b>byline</b> (the .ai-work credit) and <b>blurb</b> (the listing prose). '
       'The "Description: written by Claude" note is preserved. Rewrite any subset, '
       'press <b>Copy edits</b>, paste back into chat; Claude reassembles the frontmatter string.')


def main():
    root = fk.repo_root()
    cards = extract(root / "content" / "dwm")
    html = fk.build_html("dwm description batch editor", SUB,
                         "flubpub-description-edits-v1", "dwm-description-editor:v1", cards)
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else root / "scratch" / "description-edit-form.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print("wrote %s  (%d descriptions)" % (out, len(cards)))


if __name__ == "__main__":
    main()
