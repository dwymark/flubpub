#!/usr/bin/env python3
"""Ingest a paste-back block from either dwm prose form and apply the edits to
content/dwm. Detects the format from the sentinel line; routes per file/field.

Usage:
  python3 apply_edits.py [--dry-run] < pasted.txt
  python3 apply_edits.py [--dry-run] pasted.txt

Re-encoding is conservative: text is HTML-escaped, then a small inline-tag
whitelist (em/strong/a/code/br/i/b) is restored, and literal apostrophes /
em-dashes are left as UTF-8. Review `git diff` afterward for house-style entity
choices the script does not impose.
"""
import html, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import formkit as fk

INLINE = r"em|strong|a|code|br|i|b"


def encode(text):
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"&lt;(/?(?:%s)\b[^&]*?)&gt;" % INLINE, r"<\1>", esc)


_AIDESC_RE = re.compile(r'<span class="ai-desc"[^>]*>.*?</span>', re.S)
_KNOWN_NOTE_TIP = {fk.AI_DESC_CLAUDE_VIS: fk.AI_DESC_CLAUDE_TIP,
                   fk.AI_DESC_DANIEL_VIS: fk.AI_DESC_DANIEL_TIP}


def flip_note(desc):
    """Rewriting a blurb makes Daniel its author, so flip the .ai-desc note's
    visible text and tooltip from Claude to Daniel. Tooltip first: it contains
    the visible phrase as a substring."""
    return (desc.replace(fk.AI_DESC_CLAUDE_TIP, fk.AI_DESC_DANIEL_TIP)
                .replace(fk.AI_DESC_CLAUDE_VIS, fk.AI_DESC_DANIEL_VIS))


def apply_note(desc, note_text, label=""):
    """Swap the .ai-desc note's visible text. A known authorship phrase carries
    its canonical tooltip; arbitrary text keeps the existing tooltip."""
    note_text = note_text.strip()
    m = _AIDESC_RE.search(desc)
    if not m:
        print("  ! %s: no .ai-desc span; note edit skipped" % label)
        return desc
    tip = _KNOWN_NOTE_TIP.get(note_text)
    if tip is None:
        existing = re.search(r'title="([^"]*)"', m.group(0))
        tip = html.unescape(existing.group(1)) if existing else None
    tip_attr = ' title="%s"' % html.escape(tip, quote=True) if tip else ''
    span = '<span class="ai-desc"%s>%s</span>' % (tip_attr, encode(note_text))
    return _AIDESC_RE.sub(lambda _: span, desc, count=1)


def parse(blob):
    lines = blob.splitlines()
    sentinel = None
    for ln in lines:
        m = re.match(r"=== (flubpub-\S+) ===", ln.strip())
        if m:
            sentinel = m.group(1); break
    if not sentinel:
        sys.exit("no sentinel line found (expected '=== flubpub-...-v1 ===')")
    edits, cur_id, buf = [], None, []
    started = False
    for ln in lines:
        s = ln.strip()
        if re.match(r"=== flubpub-\S+ ===", s):
            started = True; continue
        if not started:
            continue
        if s == "=== end ===":
            break
        m = re.match(r"\[(.+)\]\s*$", ln)
        if m and " :: " in m.group(1):
            if cur_id is not None:
                edits.append((cur_id, "\n".join(buf).strip()))
            cur_id, buf = m.group(1).strip(), []
        elif cur_id is not None:
            buf.append(ln)
    if cur_id is not None:
        edits.append((cur_id, "\n".join(buf).strip()))
    return sentinel, edits


def apply_disclosures(content_dir, edits, dry):
    by_file = {}
    for fid, text in edits:
        parts = [p.strip() for p in fid.split(" :: ")]
        idx = int(parts[-1]); cls = parts[-2]; key = " :: ".join(parts[:-2])
        by_file.setdefault(key, []).append((cls, idx, text))
    changed = []
    for key, items in by_file.items():
        path = content_dir / key
        src = path.read_text(encoding="utf-8")
        out = src
        for cls, idx, text in items:
            new = encode(text)
            if cls == "note":
                pat = re.compile(r'(<div class="note"><b>(?:Who wrote this\?|Who made this\?)</b>\s*)(.*?)(</div>)', re.S)
            else:
                pat = re.compile(r'(<p class="%s">)(.*?)(</p>)' % re.escape(cls), re.S)
            n = [0]
            def repl(m):
                n[0] += 1
                return m.group(1) + new + m.group(3) if n[0] == idx else m.group(0)
            out, count = pat.subn(repl, out)
            if n[0] < idx:
                print("  ! %s: only %d match(es) of %s, wanted #%d -- skipped" % (key, n[0], cls, idx))
        if out != src:
            changed.append(key)
            if not dry:
                path.write_text(out, encoding="utf-8")
    return changed


def splice_description(desc, fields, label=""):
    """Apply byline/blurb/note edits into an existing description string,
    preserving spans not being edited."""
    if "byline" in fields:
        new = encode(fields["byline"])
        desc, c = re.subn(r'(<span class="ai-work"[^>]*>)(.*?)(</span>)',
                          lambda mm: mm.group(1) + new + mm.group(3), desc, count=1, flags=re.S)
        if not c:
            print("  ! %s: no .ai-work span; byline edit skipped" % label)
    if "blurb" in fields:
        blurb = encode(fields["blurb"])
        work = re.search(r'<span class="ai-work"[^>]*>.*?</span>', desc, re.S)
        note = re.search(r'<span class="ai-desc"[^>]*>.*?</span>', desc, re.S)
        if work and note:
            desc = desc[:work.end()].rstrip() + " " + blurb + " " + desc[note.start():].lstrip()
        elif work:
            desc = desc[:work.end()].rstrip() + " " + blurb
        elif note:
            desc = blurb + " " + desc[note.start():].lstrip()
        else:
            desc = blurb
    if "note" in fields:
        desc = apply_note(desc, fields["note"], label)
    return desc


def build_description(old_desc, fields, label=""):
    """Splice the edits, then auto-flip the .ai-desc note to Daniel when the
    blurb changed and no explicit note edit overrides it."""
    desc = splice_description(old_desc, fields, label)
    if "blurb" in fields and "note" not in fields:
        desc = flip_note(desc)
    return desc


def group_by_key(edits):
    by_key = {}
    for fid, text in edits:
        key, field = [p.strip() for p in fid.split(" :: ")]
        by_key.setdefault(key, {})[field] = text
    return by_key


def apply_descriptions(content_dir, edits, dry):
    try:
        import yaml
    except ModuleNotFoundError:
        sys.exit("needs pyyaml: run via `uv run --with pyyaml python3 apply_edits.py`")
    by_key = group_by_key(edits)
    meta = {k: v for k, v in by_key.items() if k.startswith("@meta:")}
    local = {k: v for k, v in by_key.items() if not k.startswith("@meta:")}
    changed = []
    for key, fields in local.items():
        path = content_dir / key
        src = path.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---", src, re.S)
        if not m:
            print("  ! %s: no frontmatter -- skipped" % key); continue
        fm_text = m.group(1)
        fm = yaml.safe_load(fm_text) or {}
        desc = build_description(fm.get("description", ""), fields, key)
        dumped = yaml.safe_dump({"description": desc}, allow_unicode=True, default_flow_style=False).rstrip("\n")
        lines = fm_text.split("\n")
        i = next((k for k, ln in enumerate(lines) if ln.startswith("description:")), None)
        if i is None:
            print("  ! %s: no description: key -- skipped" % key); continue
        j = i + 1
        while j < len(lines) and (lines[j][:1] in (" ", "\t")):
            j += 1
        new_fm = "\n".join(lines[:i] + dumped.split("\n") + lines[j:])
        out = src[:m.start(1)] + new_fm + src[m.end(1):]
        if out != src:
            changed.append(key)
            if not dry:
                path.write_text(out, encoding="utf-8")
    if meta:
        apply_meta_descriptions(content_dir, meta, dry)
    return changed


def apply_meta_descriptions(content_dir, meta, dry):
    """html-article descriptions live in content/<key>/_pages.yaml (the SSOT).
    Splice the edits into each slug's stored description, write _pages.yaml back,
    and publish with `flubpub --site dwm sync`. No production write here."""
    try:
        import yaml
    except ModuleNotFoundError:
        sys.exit("needs pyyaml: run via `uv run --with pyyaml python3 apply_edits.py`")
    path = content_dir / "_pages.yaml"
    if not path.is_file():
        print("  ! %s not found; cannot apply html-article edits" % path); return
    data = yaml.safe_load(path.read_text()) or {}
    changed = []
    for key, fields in meta.items():
        slug = key[len("@meta:"):]
        entry = data.get(slug) or {}
        if not entry.get("description"):
            print("  ! %s: no _pages.yaml description -- skipped" % slug); continue
        new = build_description(entry["description"], fields, slug)
        if new != entry["description"]:
            entry["description"] = new
            data[slug] = entry
            changed.append(slug)
    if changed and not dry:
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=True,
                                       default_flow_style=False), encoding="utf-8")
    verb = "would change" if dry else "changed"
    print("\n_pages.yaml: %d html-article description(s) %s%s" %
          (len(changed), verb, (": " + ", ".join(changed)) if changed else ""))
    if changed and not dry:
        print("Publish with: flubpub --site dwm sync")


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv
    blob = pathlib.Path(args[0]).read_text(encoding="utf-8") if args else sys.stdin.read()
    sentinel, edits = parse(blob)
    if not edits:
        sys.exit("no edits parsed")
    content_dir = fk.repo_root() / "content" / "dwm"
    if sentinel == "flubpub-disclosure-edits-v1":
        changed = apply_disclosures(content_dir, edits, dry)
    elif sentinel == "flubpub-description-edits-v1":
        changed = apply_descriptions(content_dir, edits, dry)
    else:
        sys.exit("unknown sentinel: " + sentinel)
    verb = "would change" if dry else "changed"
    print("%s: %d edit(s) across %d file(s) %s%s" %
          (sentinel, len(edits), len(changed), verb, ":" if changed else ""))
    for k in changed:
        print("  " + k)
    if not dry and changed:
        print("\nReview `git diff` and push with: flubpub --site dwm sync   (or per-page revise)")


if __name__ == "__main__":
    main()
