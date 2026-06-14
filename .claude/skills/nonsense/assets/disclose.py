#!/usr/bin/env python3
"""Inject a CSS-only authorship disclosure into a flubpub HTML artifact.

Three formats, all no-JS (checkbox-hack) with a persistent marker that
survives dismissal:

  banner  top-of-page strip, collapses to a compact line   (document / scrolling pages)
  stamp   corner pill, expands to an anchored panel         (immersive, free corner)
  dock    bottom-center tab, expands to a sheet             (immersive, free bottom)

Idempotent: re-running replaces a prior injection (keyed on the marker).
Banner inherits the host page palette via CSS vars (--card-bg/--bg, --fg/--ink,
--rule/--border, --accent, --prose-font/--serif); stamp and dock use a
theme-independent dark-glass chrome that reads on both light and dark art.

Usage:
  disclose.py --file content/dwm/<slug>.html --format banner \\
      --head "Who made this?" --body "<one or two sentences>" \\
      [--compact "AI-made · noted"]
  disclose.py --file ... --format stamp --corner br --head ... --body ...
  disclose.py --file ... --format dock  --head ... --body ...
"""
import argparse
import re
import sys

MARKER = "<!-- dwm-disclosure -->"
END = "<!-- /dwm-disclosure -->"
_STRIP_RE = re.compile(re.escape(MARKER) + r".*?" + re.escape(END) + r"\n?", re.S)


def banner(head, body, compact):
    return f"""{MARKER}
<style>
#dwm-disc{{position:relative;width:100%;z-index:60;}}
#dwm-disc *{{box-sizing:border-box;}}
#dwm-disc-cb{{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;}}
.dwm-disc-banner{{background:var(--card-bg,var(--bg,#f6f1e7));border-bottom:1px solid var(--rule,var(--border,#cbb89c));color:var(--fg,var(--ink,#23201a));font-family:var(--prose-font,var(--serif,Georgia,'Times New Roman',serif));}}
.dwm-disc-banner .dwm-disc-full{{max-width:42em;margin:0 auto;padding:1.2rem 1.4rem 1.1rem;}}
.dwm-disc-h{{margin:0 0 .5rem;font-size:.68rem;font-weight:700;letter-spacing:.22em;text-transform:uppercase;opacity:.6;}}
.dwm-disc-b{{margin:0 0 .85rem;font-size:.94rem;line-height:1.5;max-width:36em;}}
.dwm-disc-btn{{display:inline-block;cursor:pointer;border:1px solid currentColor;padding:.34em 1em;font-family:var(--mono-font,var(--mono,ui-monospace,Menlo,Consolas,monospace));font-size:.62rem;letter-spacing:.2em;text-transform:uppercase;opacity:.82;transition:background .15s,color .15s,border-color .15s;}}
.dwm-disc-btn:hover{{background:var(--accent,#8a5a2a);color:var(--card-bg,var(--bg,#f6f1e7));border-color:var(--accent,#8a5a2a);}}
.dwm-disc-compact{{display:none;cursor:pointer;max-width:42em;margin:0 auto;padding:.5rem 1.4rem;text-align:center;font-family:var(--mono-font,var(--mono,ui-monospace,Menlo,Consolas,monospace));font-size:.58rem;letter-spacing:.22em;text-transform:uppercase;opacity:.58;}}
.dwm-disc-compact::after{{content:" \\21BA";opacity:.7;}}
#dwm-disc-cb:checked~.dwm-disc-banner .dwm-disc-full{{display:none;}}
#dwm-disc-cb:checked~.dwm-disc-banner .dwm-disc-compact{{display:block;}}
</style>
<div id="dwm-disc">
<input type="checkbox" id="dwm-disc-cb" aria-hidden="true">
<aside class="dwm-disc-banner" role="region" aria-label="Authorship disclosure">
<div class="dwm-disc-full">
<p class="dwm-disc-h">{head}</p>
<p class="dwm-disc-b">{body}</p>
<label for="dwm-disc-cb" class="dwm-disc-btn" tabindex="0">Noted</label>
</div>
<label for="dwm-disc-cb" class="dwm-disc-compact" tabindex="0">{compact}</label>
</aside>
</div>
{END}"""


_CORNER = {
    "tr": "top:.6rem;right:.6rem;",
    "br": "bottom:.6rem;right:.6rem;",
    "tl": "top:.6rem;left:.6rem;",
    "bl": "bottom:.6rem;left:.6rem;",
}


def stamp(head, body, corner):
    pos = _CORNER[corner]
    return f"""{MARKER}
<style>
#dwm-disc{{position:fixed;{pos}z-index:2147483000;display:flex;flex-direction:column;font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;}}
#dwm-disc *{{box-sizing:border-box;}}
#dwm-disc-cb{{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;}}
#dwm-disc .dwm-disc-pill{{display:none;align-items:center;gap:.4em;cursor:pointer;font-size:.7rem;letter-spacing:.04em;padding:.36em .75em;border-radius:999px;background:rgba(18,18,20,.82);color:#f2efe6;border:1px solid rgba(255,255,255,.25);box-shadow:0 2px 12px rgba(0,0,0,.35);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);user-select:none;white-space:nowrap;}}
#dwm-disc .dwm-disc-pill:hover{{background:rgba(18,18,20,.96);}}
#dwm-disc .dwm-disc-panel{{display:block;width:min(23rem,calc(100vw - 1.4rem));background:rgba(16,16,18,.97);color:#f2efe6;border:1px solid rgba(255,255,255,.2);border-radius:12px;padding:1.05rem 1.1rem .95rem;box-shadow:0 12px 40px rgba(0,0,0,.5);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);}}
#dwm-disc .dwm-disc-h{{margin:0 0 .5rem;font-size:.58rem;font-weight:700;letter-spacing:.2em;text-transform:uppercase;opacity:.6;}}
#dwm-disc .dwm-disc-b{{margin:0 0 .85rem;font-family:Georgia,'Times New Roman',serif;font-size:.9rem;line-height:1.5;}}
#dwm-disc .dwm-disc-btn{{display:inline-block;cursor:pointer;font-size:.58rem;letter-spacing:.18em;text-transform:uppercase;padding:.42em .95em;border:1px solid rgba(242,239,230,.5);color:#f2efe6;border-radius:7px;}}
#dwm-disc .dwm-disc-btn:hover{{background:#f2efe6;color:#121214;}}
#dwm-disc-cb:checked~.dwm-disc-pill{{display:inline-flex;}}
#dwm-disc-cb:checked~.dwm-disc-panel{{display:none;}}
</style>
<div id="dwm-disc">
<input type="checkbox" id="dwm-disc-cb" aria-hidden="true">
<label for="dwm-disc-cb" class="dwm-disc-pill" tabindex="0">\U0001F916 AI-made</label>
<div class="dwm-disc-panel" role="region" aria-label="Authorship disclosure">
<p class="dwm-disc-h">{head}</p>
<p class="dwm-disc-b">{body}</p>
<label for="dwm-disc-cb" class="dwm-disc-btn" tabindex="0">Noted</label>
</div>
</div>
{END}"""


def dock(head, body):
    return f"""{MARKER}
<style>
#dwm-disc{{position:fixed;left:50%;bottom:0;transform:translateX(-50%);z-index:2147483000;display:flex;flex-direction:column;align-items:center;font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;}}
#dwm-disc *{{box-sizing:border-box;}}
#dwm-disc-cb{{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;}}
#dwm-disc .dwm-disc-tab{{display:none;cursor:pointer;font-size:.68rem;letter-spacing:.05em;padding:.4em .95em;border-radius:9px 9px 0 0;background:rgba(18,18,20,.85);color:#f2efe6;border:1px solid rgba(255,255,255,.22);border-bottom:none;box-shadow:0 -2px 12px rgba(0,0,0,.3);white-space:nowrap;}}
#dwm-disc .dwm-disc-tab:hover{{background:rgba(18,18,20,.96);}}
#dwm-disc .dwm-disc-sheet{{display:block;width:min(30rem,calc(100vw - 1rem));background:rgba(16,16,18,.97);color:#f2efe6;border:1px solid rgba(255,255,255,.2);border-bottom:none;border-radius:12px 12px 0 0;padding:1.05rem 1.2rem 1rem;box-shadow:0 -8px 40px rgba(0,0,0,.45);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);}}
#dwm-disc .dwm-disc-h{{margin:0 0 .5rem;font-size:.58rem;font-weight:700;letter-spacing:.2em;text-transform:uppercase;opacity:.6;}}
#dwm-disc .dwm-disc-b{{margin:0 0 .85rem;font-family:Georgia,'Times New Roman',serif;font-size:.9rem;line-height:1.5;}}
#dwm-disc .dwm-disc-btn{{display:inline-block;cursor:pointer;font-size:.58rem;letter-spacing:.18em;text-transform:uppercase;padding:.42em .95em;border:1px solid rgba(242,239,230,.5);color:#f2efe6;border-radius:7px;}}
#dwm-disc .dwm-disc-btn:hover{{background:#f2efe6;color:#121214;}}
#dwm-disc-cb:checked~.dwm-disc-tab{{display:inline-block;}}
#dwm-disc-cb:checked~.dwm-disc-sheet{{display:none;}}
</style>
<div id="dwm-disc">
<input type="checkbox" id="dwm-disc-cb" aria-hidden="true">
<div class="dwm-disc-sheet" role="region" aria-label="Authorship disclosure">
<p class="dwm-disc-h">{head}</p>
<p class="dwm-disc-b">{body}</p>
<label for="dwm-disc-cb" class="dwm-disc-btn" tabindex="0">Noted</label>
</div>
<label for="dwm-disc-cb" class="dwm-disc-tab" tabindex="0">\U0001F916 AI-made</label>
</div>
{END}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True)
    ap.add_argument("--format", required=True, choices=["banner", "stamp", "dock"])
    ap.add_argument("--head", default="Who made this?")
    ap.add_argument("--body", required=True)
    ap.add_argument("--corner", default="br", choices=list(_CORNER))
    ap.add_argument("--compact", default="AI-made · noted")
    a = ap.parse_args()

    if a.format == "banner":
        snippet = banner(a.head, a.body, a.compact)
    elif a.format == "stamp":
        snippet = stamp(a.head, a.body, a.corner)
    else:
        snippet = dock(a.head, a.body)

    s = open(a.file, encoding="utf-8").read()
    s = _STRIP_RE.sub("", s)
    if a.format == "banner":
        m = re.search(r"<body[^>]*>", s, re.I)
        if not m:
            sys.exit(f"no <body> tag in {a.file} (banner needs one; use stamp/dock for tagless docs)")
        s = s[:m.end()] + "\n" + snippet + "\n" + s[m.end():]
    else:
        ends = list(re.finditer(r"</body\s*>", s, re.I))
        if ends:
            i = ends[-1].start()
            s = s[:i] + snippet + "\n" + s[i:]
        else:  # tagless minimal HTML: append as last body child
            s = s.rstrip("\n") + "\n" + snippet + "\n"
    open(a.file, "w", encoding="utf-8").write(s)
    print(f"disclosed ({a.format}) -> {a.file}")


if __name__ == "__main__":
    main()
