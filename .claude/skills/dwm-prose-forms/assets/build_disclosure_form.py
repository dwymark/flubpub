#!/usr/bin/env python3
"""Extract every Claude-authored authorship disclosure in content/dwm and emit
the palm-eink illuminated batch-edit form. Paste-back ingested by apply_edits.py.

Usage: python3 build_disclosure_form.py [OUT_HTML]   (default: <repo>/scratch/disclosure-edit-form.html)
"""
import re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import formkit as fk

# body-paragraph and heading classes across the five disclosure variants
BODY_CLASSES = ["dwm-disc-b", "hl-disc-b", "provenance-body", "provenance-behavior", "disc-body"]
HEAD_CLASSES = ["dwm-disc-h", "hl-disc-h", "provenance-header", "disc-header"]


def title_of(path, text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    if m:
        t = re.search(r"^title:\s*(.+)$", m.group(1), re.M)
        if t:
            return t.group(1).strip().strip("\"'")
    t = re.search(r"<title>(.*?)</title>", text, re.S)
    return fk.decode(t.group(1)) if t else path.stem


def extract(content_dir):
    cards = []
    for p in sorted(q for q in content_dir.rglob("*") if q.suffix in (".md", ".html")):
        text = p.read_text(encoding="utf-8")
        low = text.lower()
        if "who wrote this" not in low and "who made this" not in low:
            continue
        key = str(p.relative_to(content_dir))
        heading = None
        for hc in HEAD_CLASSES:
            m = re.search(r'<p class="%s">(.*?)</p>' % re.escape(hc), text)
            if m:
                heading = fk.decode(m.group(1)); break
        spans = []
        for bc in BODY_CLASSES:
            for m in re.finditer(r'<p class="%s">(.*?)</p>' % re.escape(bc), text, re.S):
                spans.append((m.start(), bc, m.group(1)))
        for m in re.finditer(r'<div class="note"><b>(Who wrote this\?|Who made this\?)</b>\s*(.*?)</div>', text, re.S):
            if heading is None:
                heading = fk.decode(m.group(1))
            spans.append((m.start(), "note", m.group(2)))
        spans.sort()
        counts, fields = {}, []
        for _pos, cls, raw in spans:
            counts[cls] = counts.get(cls, 0) + 1
            fields.append({
                "id": "%s :: %s :: %d" % (key, cls, counts[cls]),
                "label": "%s #%d" % (cls, counts[cls]),
                "value": fk.decode(raw),
                "multiline": True,
            })
        if heading is None:
            m = re.search(r">(Who wrote this\?|Who made this\?)<", text)
            heading = m.group(1) if m else "Who wrote this?"
        if fields:
            cards.append({"key": key, "title": title_of(p, text), "tag": heading, "fields": fields})
    return cards


SUB = ('Every Claude-authored authorship disclosure in <code>content/dwm/</code>. '
       'Rewrite the prose of any subset; only changed fields export. Press <b>Copy edits</b> '
       'and paste back into chat. Entities and inline markup are decoded for editing; '
       'Claude re-encodes on write-back.')


def main():
    root = fk.repo_root()
    cards = extract(root / "content" / "dwm")
    html = fk.build_html("dwm disclosure batch editor", SUB,
                         "flubpub-disclosure-edits-v1", "dwm-disclosure-editor:v1", cards)
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else root / "scratch" / "disclosure-edit-form.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    n = sum(len(c["fields"]) for c in cards)
    print("wrote %s  (%d disclosures, %d paragraphs)" % (out, len(cards), n))


if __name__ == "__main__":
    main()
