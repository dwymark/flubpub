#!/usr/bin/env python3
"""Extract the listing description: of every dwm article and emit the palm-eink
illuminated batch-edit form. Each description splits into byline (.ai-work) and
blurb. Paste-back ingested by apply_edits.py.

Two sources, both in one form:
  - .md articles: the frontmatter `description:` (the version-controlled SSOT).
  - html-bundle articles: the listing description from production `pages.json`,
    which lives only on the box (cards keyed `@prod:<slug>`, written back via
    `flubpub --site dwm revise`).

Usage: python3 build_description_form.py [OUT_HTML]   (default: <repo>/scratch/description-edit-form.html)
       FLUBPUB_FORMS_NO_REMOTE=1  -> skip the pages.json pull (md-only form)
"""
import os, re, sys, pathlib
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
        "fields": [
            {"id": "%s :: byline" % key, "label": "byline (.ai-work)", "value": byline, "multiline": False},
            {"id": "%s :: blurb" % key, "label": "blurb", "value": blurb, "multiline": True},
        ],
        "foot": ("preserved note: " + note) if note else "",
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


def extract_prod(content_dir, md_slugs):
    """html-article descriptions from production pages.json (slugs without a
    frontmatter-description .md). Returns (cards, status_message)."""
    pages = fk.fetch_prod_pages("dwm")
    if pages is None:
        return [], "remote pages.json unavailable (set FLUBPUB_FORMS_NO_REMOTE=1 to silence) -- md-only"
    cards = []
    for pg in pages:
        slug, desc = pg.get("slug"), pg.get("description")
        if not slug or not desc or slug in md_slugs:
            continue
        cf = fk.content_file_for(content_dir, slug)
        if cf is None:
            continue  # no content/dwm bundle to revise from -- skip
        byline, blurb, note = split_desc(desc)
        cards.append(make_card("@prod:" + slug, pg.get("title", slug), byline, blurb, note,
                               tag="prod · pages.json"))
    return cards, "pulled %d html-article description(s) from prod pages.json" % len(cards)


SUB = ('The listing <code>description:</code> of every dwm article, split into '
       '<b>byline</b> (.ai-work credit) and <b>blurb</b> (the listing prose). '
       '<b>.md</b> articles come from frontmatter (the SSOT); <b>prod &middot; pages.json</b> '
       'cards are html bundles whose description lives only on the box. The '
       '"Description: written by Claude" note is preserved. Rewrite any subset, '
       'press <b>Copy edits</b>, paste back into chat.')


def main():
    root = fk.repo_root()
    content_dir = root / "content" / "dwm"
    cards, md_slugs = extract_md(content_dir)
    n_md = len(cards)
    n_prod = 0
    if os.environ.get("FLUBPUB_FORMS_NO_REMOTE"):
        status = "remote pull skipped (FLUBPUB_FORMS_NO_REMOTE) -- md-only"
    else:
        prod, status = extract_prod(content_dir, md_slugs)
        cards += prod
        n_prod = len(prod)
    html = fk.build_html("dwm description batch editor", SUB,
                         "flubpub-description-edits-v1", "dwm-description-editor:v1", cards)
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else root / "scratch" / "description-edit-form.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print("wrote %s  (%d md + %d prod = %d descriptions)" % (out, n_md, n_prod, len(cards)))
    print("  " + status)


if __name__ == "__main__":
    main()
