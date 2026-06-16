#!/usr/bin/env python3
"""Extract the listing description: of every dwm article and emit the palm-eink
illuminated batch-edit form. Each description splits into byline (.ai-work),
blurb, and note (.ai-desc). Paste-back ingested by apply_edits.py.

Two sources, both in one form, both version-controlled SSOT:
  - .md articles: the frontmatter `description:`.
  - html articles: content/<key>/_pages.yaml (cards keyed `@meta:<slug>`),
    written back to _pages.yaml and published via `flubpub --site dwm sync`.

Usage: python3 build_description_form.py [OUT_HTML]   (default: <repo>/scratch/description-edit-form.html)
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


def split_desc(desc):
    _bt, byline = grab("ai-work", desc)
    _dt, note = grab("ai-desc", desc)
    blurb = fk.decode(re.sub(r'<span class="ai-(work|desc)"[^>]*>.*?</span>', "", desc, flags=re.S))
    return byline or "", blurb, note


def make_card(key, title, byline, blurb, note, tag=None):
    return {
        "key": key,
        "title": title,
        "tag": tag,
        "note_autoflip": fk.AI_DESC_DANIEL_VIS,
        "fields": [
            {"id": "%s :: byline" % key, "role": "byline", "label": "byline (.ai-work)", "value": byline, "multiline": False},
            {"id": "%s :: blurb" % key, "role": "blurb", "label": "blurb", "value": blurb, "multiline": True},
            {"id": "%s :: note" % key, "role": "note", "label": "note (.ai-desc)", "value": note or "", "multiline": False},
        ],
    }


def extract_md(content_dir):
    cards, md_slugs = [], set()
    for p in sorted(content_dir.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---", text, re.S)
        if not m:
            continue
        fm = yaml.safe_load(m.group(1)) or {}
        desc = fm.get("description")
        if not desc:
            continue
        md_slugs.add(p.stem)
        byline, blurb, note = split_desc(desc)
        cards.append(make_card(p.name, fm.get("title", p.stem), byline, blurb, note))
    return cards, md_slugs


def extract_meta(content_dir, md_slugs):
    """html-article descriptions from content/<key>/_pages.yaml (the SSOT). Cards
    keyed @meta:<slug>. Returns (cards, status_message)."""
    path = content_dir / "_pages.yaml"
    if not path.is_file():
        return [], "no _pages.yaml found -- md-only"
    data = yaml.safe_load(path.read_text()) or {}
    cards = []
    for slug in sorted(data):
        meta = data[slug] or {}
        desc = meta.get("description")
        if not desc or slug in md_slugs:
            continue
        byline, blurb, note = split_desc(desc)
        cards.append(make_card("@meta:" + slug, meta.get("title", slug), byline, blurb, note,
                               tag="html · _pages.yaml"))
    return cards, "loaded %d html-article description(s) from _pages.yaml" % len(cards)


SUB = ('The listing <code>description:</code> of every dwm article, split into '
       'three editable fields: <b>byline</b> (.ai-work work credit), <b>blurb</b> '
       '(the listing prose), and <b>note</b> (.ai-desc, who wrote the blurb). '
       '<b>.md</b> articles come from frontmatter; <b>html &middot; _pages.yaml</b> '
       'cards come from the SSOT metadata file. Rewriting a blurb auto-flips its '
       'note to Daniel; the byline never auto-changes. Rewrite any subset, press '
       '<b>Copy edits</b>, paste back into chat.')


def main():
    root = fk.repo_root()
    content_dir = root / "content" / "dwm"
    cards, md_slugs = extract_md(content_dir)
    n_md = len(cards)
    meta, status = extract_meta(content_dir, md_slugs)
    cards += meta
    n_meta = len(meta)
    html = fk.build_html("dwm description batch editor", SUB,
                         "flubpub-description-edits-v1", "dwm-description-editor:v1", cards)
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else root / "scratch" / "description-edit-form.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print("wrote %s  (%d md + %d html = %d descriptions)" % (out, n_md, n_meta, len(cards)))
    print("  " + status)


if __name__ == "__main__":
    main()
