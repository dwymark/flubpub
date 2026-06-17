#!/usr/bin/env python3
"""Generate the Strange Interlocutor hub and its no-JS theme variants.

Maintenance surface is three files:
  - content.jsonl      the canonical content (one JSON object per line)
  - templates/         the page template (readable HTML/CSS/JS with Jinja holes)
  - this script         wiring + per-variant background assets

Outputs (into the parent dir, i.e. content/dwm/):
  - strange-interlocutor.html        the JS hub (deck + live chooser). With JS off
                                     it falls back to the Animated stacked column.
  - strange-interlocutor-retro.html  static no-JS Retro variant
  - strange-interlocutor-plain.html  static no-JS Plain variant

The three variants differ only in: which static background they carry, which
theme link is "depressed", and which rendition the essay links point at. All of
that is data; the template is shared.

Run:  python3 build.py            (writes into ../, i.e. content/dwm/)
      python3 build.py OUTDIR     (writes into OUTDIR instead, for testing)
"""
import json
import pathlib
import sys
from jinja2 import Environment, FileSystemLoader

ROOT = pathlib.Path(__file__).resolve().parent
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent


def load_jsonl(path):
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def asset(name):
    return (ROOT / "assets" / name).read_text().strip()


def cover(b64, mime):
    return ('background:#eef4f5 center center / cover no-repeat;'
            'background-image:url("data:image/%s;base64,%s")' % (mime, b64))


def main():
    recs = load_jsonl(ROOT / "content.jsonl")
    by = lambda t: [r for r in recs if r["type"] == t]
    one = lambda t: next(r for r in recs if r["type"] == t)

    meta = one("meta")
    themes = by("theme")
    pieces = by("piece")
    artifacts = by("artifact")
    artifacts_meta = one("artifacts_meta")
    depictions = by("depiction")
    contrib = by("contrib")
    note = one("note")["text"]

    wallpaper_uri = "data:image/svg+xml;base64," + asset("wallpaper.b64")
    bg_by_key = {
        "shader": cover(asset("frozen-animated.b64"), "jpeg"),
        "palm": cover(asset("frozen-retro.b64"), "jpeg"),
        "wallpaper": ('background-color:#eef4f5;background-repeat:repeat;'
                      'background-size:200px 200px;background-image:url("%s")' % wallpaper_uri),
    }

    # (theme key, is it the JS hub?). The JS hub is the Animated variant; the
    # other two are static pages whose only job is the no-JS reading experience.
    jobs = [("shader", True), ("palm", False), ("wallpaper", False)]
    tmap = {t["key"]: t for t in themes}

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      autoescape=False, trim_blocks=True, lstrip_blocks=True)
    tpl = env.get_template("hub.html.j2")

    for key, js_hub in jobs:
        theme = tmap[key]
        html = tpl.render(meta=meta, themes=themes, theme=theme, js_hub=js_hub,
                          pieces=pieces, artifacts=artifacts, artifacts_meta=artifacts_meta,
                          depictions=depictions, contrib=contrib, note=note,
                          bg_decl=bg_by_key[key], wallpaper_uri=wallpaper_uri)
        dest = OUT / (theme["slug"] + ".html")
        dest.write_text(html)
        print("wrote %s (%d bytes, js_hub=%s)" % (dest.name, len(html), js_hub))


if __name__ == "__main__":
    main()
