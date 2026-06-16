"""Shared kit for the dwm prose paste-back forms: repo discovery, registry /
remote helpers, the palm-eink illuminated template, and a generic card/field
renderer.

A card is {key, title, tag?, foot?, fields:[{id, label, value, multiline}]}.
Each field's id IS its export key (the bracket contents in the paste-back).
"""
import html, json, os, pathlib, re, subprocess


def repo_root(start=None):
    p = pathlib.Path(start or __file__).resolve()
    for anc in [p] + list(p.parents):
        if (anc / "content" / "dwm").is_dir():
            return anc
    raise SystemExit("could not locate repo root (no content/dwm above " + str(p) + ")")


def decode(s):
    return html.unescape(re.sub(r"\s+", " ", s)).strip()


# Canonical .ai-desc authorship phrases (visible text + tooltip), shared by the
# form builder and the apply script. The blurb's author owns its one-line
# description, so rewriting a blurb flips this note to Daniel.
AI_DESC_CLAUDE_VIS = "Description: written by Claude"
AI_DESC_DANIEL_VIS = "Description: written by Daniel Wymark"
AI_DESC_CLAUDE_TIP = "This one-line description was written by Claude (Anthropic)."
AI_DESC_DANIEL_TIP = "This one-line description was written by Daniel Wymark."


# --- registry / remote helpers (for prod pages.json: html-article descriptions) ---

def registry_path():
    return pathlib.Path(os.environ.get("FLUBPUB_SITES_CONFIG",
                                       pathlib.Path.home() / ".config" / "flubpub" / "sites.json"))


def site_remote(key="dwm"):
    """Return (ssh_target, remote_dir) for a registry site key, or (None, None)."""
    cfg = registry_path()
    if not cfg.is_file():
        return None, None
    spec = (json.loads(cfg.read_text()).get("sites", {}).get(key, {}) or {}).get("remote")
    if not spec or ":" not in spec:
        return None, None
    target, remote_dir = spec.split(":", 1)
    return target, remote_dir


def fetch_prod_pages(key="dwm"):
    """SSH-read the production pages.json for a site. Returns the list of page
    dicts, or None on any failure (caller degrades to local-only)."""
    target, remote_dir = site_remote(key)
    if not target:
        return None
    cmd = ["ssh", "-o", "ConnectTimeout=12", "-o", "BatchMode=yes",
           target, "cat %s/data/pages.json" % remote_dir]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        data = data.get("pages", list(data.values()))
    return data if isinstance(data, list) else None


def content_file_for(content_dir, slug):
    """Resolve the content/dwm entry file for a published slug, or None."""
    for cand in (content_dir / (slug + ".html"),
                 content_dir / slug / "index.html",
                 content_dir / slug / (slug + ".html")):
        if cand.is_file():
            return cand
    return None


STYLE = r"""
  :root{
    --ink:#2c2216; --paper:#f5edd9; --parch-card:#f7f1e0;
    --g1:#ebe0c6; --g2:#d9c9a4; --g3:#9c8a64; --g4:#6f5d3b; --g5:#352a1a;
    --blue:#27468f; --blue-deep:#1d3570; --red:#b23a24;
    --gold:#c39a2e; --gold-lt:#d8b347; --green:#5e7338;
    --bezant: radial-gradient(circle at 5px 50%, var(--gold) 2.4px, transparent 3px);
    --corner: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200%2018%2018%27%3E%3Cg%20fill%3D%27%23c39a2e%27%20stroke%3D%27%232c2216%27%20stroke-width%3D%271%27%3E%3Ccircle%20cx%3D%276%27%20cy%3D%276%27%20r%3D%273.2%27%2F%3E%3Ccircle%20cx%3D%2712%27%20cy%3D%276%27%20r%3D%273.2%27%2F%3E%3Ccircle%20cx%3D%276%27%20cy%3D%2712%27%20r%3D%273.2%27%2F%3E%3Ccircle%20cx%3D%2712%27%20cy%3D%2712%27%20r%3D%273.2%27%2F%3E%3Ccircle%20cx%3D%279%27%20cy%3D%279%27%20r%3D%272.2%27%20fill%3D%27%23b23a24%27%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E");
    --mono:ui-monospace,"SF Mono",Menlo,"Courier New",monospace;
    --serif:"Hoefler Text",Georgia,"Times New Roman",serif;
  }
  *{box-sizing:border-box;}
  body{margin:0;background:var(--g2);color:var(--ink);
       font-family:-apple-system,"Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:1.45;padding:0 0 7rem;}
  .sheet{max-width:62em;margin:0 auto;background:var(--paper);
         border-left:2px solid var(--ink);border-right:2px solid var(--ink);min-height:100vh;}
  header{position:sticky;top:0;z-index:5;background:var(--paper);border-bottom:2px solid var(--gold);}
  .titlebar{background:var(--blue);color:var(--gold-lt);display:flex;align-items:center;gap:.65rem;padding:9px 14px;}
  .mark{flex:0 0 auto;width:24px;height:24px;background:var(--corner) center/contain no-repeat;}
  h1{margin:0;font-family:var(--mono);font-weight:700;font-size:1rem;letter-spacing:.12em;text-transform:uppercase;}
  .hdr-body{padding:.7rem 14px .85rem;}
  .sub{margin:0;color:var(--g4);font-size:.84rem;max-width:58em;}
  .sub code{font-family:var(--mono);color:var(--ink);}
  .seam{height:14px;border-top:1.5px solid var(--gold);background-image:var(--bezant);
        background-size:var(--pitch,11px) 100%;background-repeat:repeat-x;}
  .controls{display:flex;gap:.55rem;align-items:center;flex-wrap:wrap;padding:.7rem 14px;}
  .controls input[type=search]{background:var(--parch-card);border:2px solid var(--ink);color:var(--ink);
        font-family:var(--mono);font-size:.8rem;padding:.45em .7em;border-radius:0;min-width:16em;}
  .controls input[type=search]:focus{outline:none;border-color:var(--blue);}
  .btn-chrome{font-family:var(--mono);font-weight:700;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;
        background:var(--parch-card);color:var(--ink);border:2px solid var(--ink);border-radius:0;
        box-shadow:3px 3px 0 var(--ink);padding:.5em .9em;cursor:pointer;}
  .btn-chrome:active{transform:translate(3px,3px);box-shadow:none;background:var(--ink);color:var(--paper);}
  .btn-chrome[aria-pressed=true]{background:var(--blue);color:var(--gold-lt);box-shadow:3px 3px 0 var(--gold);border-color:var(--ink);}
  main{padding:1.1rem 14px;}
  .card{background:var(--parch-card);border:2px solid var(--ink);border-radius:0;box-shadow:3px 3px 0 var(--ink);
        margin:0 0 1.3rem;padding:.85rem 1.05rem 1rem;}
  .card.changed{box-shadow:3px 3px 0 var(--gold);outline:2px solid var(--gold);outline-offset:2px;}
  .card.hidden{display:none;}
  .card-head{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;margin-bottom:.55rem;flex-wrap:wrap;}
  .key{font-family:var(--mono);font-weight:700;font-size:.9rem;color:var(--ink);word-break:break-all;}
  .title{color:var(--g4);font-style:italic;font-family:var(--serif);font-size:.88rem;}
  .tag{display:inline-block;font-family:var(--mono);font-size:.64rem;letter-spacing:.16em;text-transform:uppercase;
        color:var(--red);border:1.5px solid var(--gold);padding:.18em .6em;margin-bottom:.7rem;}
  .tag::before{content:"\00B6 ";}
  .foot{font-family:var(--mono);font-size:.62rem;color:var(--g4);margin:.55rem 0 0;}
  .field{margin:0 0 .9rem;}
  .field:last-child{margin-bottom:.2rem;}
  .field-meta{display:flex;justify-content:space-between;align-items:center;gap:.6rem;margin-bottom:.32rem;}
  .lbl{font-family:var(--mono);font-size:.64rem;letter-spacing:.14em;text-transform:uppercase;color:var(--red);}
  .lbl .dot{display:inline-block;width:.62em;height:.62em;border-radius:50%;background:var(--g3);margin-left:.45em;vertical-align:middle;}
  .field.changed .lbl .dot{background:var(--gold);box-shadow:0 0 0 1px var(--ink);}
  .revert{background:none;border:none;color:var(--g4);font-family:var(--mono);font-size:.66rem;cursor:pointer;
        text-decoration:underline;visibility:hidden;}
  .field.changed .revert{visibility:visible;}
  .revert:hover{color:var(--red);}
  textarea,.line{width:100%;background:var(--parch-card);border:2px solid var(--ink);color:var(--ink);
        font-family:var(--serif);font-size:.98rem;line-height:1.5;padding:.55em .75em;border-radius:0;}
  textarea{resize:vertical;min-height:3.2em;}
  .line{font-size:.92rem;}
  textarea:focus,.line:focus{outline:none;border-color:var(--blue);}
  .field.changed textarea,.field.changed .line{border-color:var(--gold);}
  footer{position:fixed;bottom:0;left:0;right:0;background:var(--g5);border-top:2px solid var(--gold);padding:.8rem 14px;
        display:flex;align-items:center;gap:1rem;flex-wrap:wrap;z-index:6;}
  .count{font-family:var(--mono);font-size:.82rem;color:var(--g1);letter-spacing:.04em;}
  .count b{display:inline-block;background:var(--red);color:var(--paper);border:1.5px solid var(--gold);padding:.05em .5em;font-weight:700;}
  #copy{font-family:var(--mono);font-weight:700;font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;
        background:var(--blue);color:var(--gold-lt);border:2px solid var(--ink);border-radius:0;box-shadow:3px 3px 0 var(--gold);
        padding:.55em 1.4em;cursor:pointer;}
  #copy:active{transform:translate(3px,3px);box-shadow:none;}
  #copy:disabled{background:var(--g4);color:var(--g2);box-shadow:none;border-style:dotted;cursor:default;}
  #toast{font-family:var(--mono);font-size:.78rem;letter-spacing:.03em;}
  #toast[data-ok="1"]{color:var(--gold-lt);}
  #toast[data-ok="0"]{color:#e09a86;}
  #export-pre{flex-basis:100%;background:var(--parch-card);border:2px solid var(--ink);color:var(--ink);font-family:var(--mono);
        font-size:.76rem;padding:.7em;max-height:14em;overflow:auto;white-space:pre-wrap;margin:.4rem 0 0;}
"""

SCRIPT = r"""
const DATA = __DATA__;
const SENTINEL = "__SENTINEL__";
const STORAGE_KEY = "__STORAGE__";
function loadSaved(){ try{ return JSON.parse(localStorage.getItem(STORAGE_KEY)||"{}"); }catch(e){ return {}; } }
function save(s){ try{ localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); }catch(e){} }
let saved = loadSaved();
const list = document.getElementById("list");
function autosize(ta){ ta.style.height="auto"; ta.style.height=(ta.scrollHeight+2)+"px"; }

DATA.forEach(d => {
  const card=document.createElement("section"); card.className="card"; card.dataset.key=d.key;
  const head=document.createElement("div"); head.className="card-head";
  head.innerHTML='<span class="key"></span><span class="title"></span>';
  head.querySelector(".key").textContent=d.key;
  head.querySelector(".title").textContent=d.title||"";
  card.appendChild(head);
  if(d.tag){ const t=document.createElement("span"); t.className="tag"; t.textContent=d.tag; card.appendChild(t); }
  const roleInputs={};
  d.fields.forEach(f => {
    const wrap=document.createElement("div"); wrap.className="field"; wrap.dataset.id=f.id;
    const meta=document.createElement("div"); meta.className="field-meta";
    meta.innerHTML='<span class="lbl"></span><button class="revert" type="button">revert</button>';
    meta.querySelector(".lbl").append(document.createTextNode(f.label));
    const dot=document.createElement("span"); dot.className="dot"; meta.querySelector(".lbl").appendChild(dot);
    let inp;
    if(f.multiline){ inp=document.createElement("textarea"); }
    else { inp=document.createElement("input"); inp.type="text"; inp.className="line"; }
    inp.value=(f.id in saved)?saved[f.id]:f.value;
    inp.dataset.orig=f.value;
    roleInputs[f.role||f.id.split(" :: ").pop()]=inp;
    wrap.appendChild(meta); wrap.appendChild(inp); card.appendChild(wrap);
    const sync=()=>{ const c=inp.value.trim()!==f.value.trim(); wrap.classList.toggle("changed",c);
      if(c) saved[f.id]=inp.value; else delete saved[f.id]; save(saved); refresh(); };
    inp.addEventListener("input",()=>{ if(f.multiline) autosize(inp); sync(); });
    meta.querySelector(".revert").addEventListener("click",()=>{ inp.value=f.value; if(f.multiline) autosize(inp); sync(); });
    if(f.multiline) requestAnimationFrame(()=>autosize(inp));
  });
  // "During edits" cue: rewriting a blurb flips its .ai-desc note to Daniel.
  // Leaves a hand-edited note (anything other than the original or the flip
  // target) alone; reverts when the blurb is reverted.
  const blurbInp=roleInputs["blurb"], noteInp=roleInputs["note"];
  if(blurbInp && noteInp && d.note_autoflip){
    const flip=d.note_autoflip, noteOrig=noteInp.dataset.orig, blurbOrig=blurbInp.dataset.orig;
    blurbInp.addEventListener("input",()=>{
      if(noteInp.value!==noteOrig && noteInp.value!==flip) return;
      const want=(blurbInp.value.trim()!==blurbOrig.trim())?flip:noteOrig;
      if(noteInp.value!==want){ noteInp.value=want; noteInp.dispatchEvent(new Event("input")); }
    });
  }
  if(d.foot){ const n=document.createElement("p"); n.className="foot"; n.textContent=d.foot; card.appendChild(n); }
  list.appendChild(card);
});

function changedFields(){
  const out=[];
  DATA.forEach(d => d.fields.forEach(f => {
    if(f.id in saved && saved[f.id].trim()!==f.value.trim()) out.push({id:f.id, text:saved[f.id].trim()});
  }));
  return out;
}
function refresh(){
  const ch=changedFields();
  document.getElementById("n").textContent=ch.length;
  document.getElementById("copy").disabled=ch.length===0;
  document.querySelectorAll(".card").forEach(c=>c.classList.toggle("changed",!!c.querySelector(".field.changed")));
  applyFilter();
}
function buildExport(){
  let s="=== "+SENTINEL+" ===\n";
  changedFields().forEach(f => { s+="\n["+f.id+"]\n"+f.text+"\n"; });
  s+="\n=== end ===\n";
  return s;
}
async function copyToClipboard(text){
  try{ if(navigator.clipboard&&navigator.clipboard.writeText){ await navigator.clipboard.writeText(text); return {ok:true}; } }catch(e){}
  const ta=document.createElement("textarea"); ta.value=text; ta.style.cssText="position:fixed;opacity:0;pointer-events:none;";
  document.body.appendChild(ta); ta.select(); let ok=false; try{ ok=document.execCommand("copy"); }catch(e){}
  document.body.removeChild(ta); return {ok};
}
function showToast(m,ok){ const el=document.getElementById("toast"); el.textContent=m; el.dataset.ok=ok?"1":"0"; setTimeout(()=>{el.textContent="";},4000); }
function showFallbackPre(t){ let p=document.getElementById("export-pre"); if(!p){ p=document.createElement("pre"); p.id="export-pre"; document.querySelector("footer").appendChild(p); } p.textContent=t; }
document.getElementById("copy").addEventListener("click", async ()=>{
  const t=buildExport(); const r=await copyToClipboard(t);
  if(r.ok) showToast("Copied "+changedFields().length+" edit(s). Paste into chat.", true);
  else { showToast("Clipboard blocked. Copy from the box below.", false); showFallbackPre(t); }
});
let changedOnly=false;
function applyFilter(){
  const q=document.getElementById("filter").value.trim().toLowerCase();
  document.querySelectorAll(".card").forEach(c=>{
    const hitQ=!q||c.textContent.toLowerCase().includes(q);
    const hitC=!changedOnly||c.classList.contains("changed");
    c.classList.toggle("hidden", !(hitQ&&hitC));
  });
}
document.getElementById("filter").addEventListener("input", applyFilter);
document.getElementById("changed-only").addEventListener("click", e=>{ changedOnly=!changedOnly; e.currentTarget.setAttribute("aria-pressed", changedOnly?"true":"false"); applyFilter(); });
document.getElementById("reset-all").addEventListener("click", ()=>{
  if(!confirm("Revert every field to its current on-page value?")) return;
  saved={}; save(saved);
  document.querySelectorAll("textarea,.line").forEach(inp=>{ inp.value=inp.dataset.orig; if(inp.tagName==="TEXTAREA") autosize(inp); inp.closest(".field").classList.remove("changed"); });
  refresh();
});
refresh();
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>__STYLE__</style>
</head>
<body>
<div class="sheet">
<header>
  <div class="titlebar"><span class="mark" aria-hidden="true"></span><h1>__TITLE__</h1></div>
  <div class="hdr-body"><p class="sub">__SUBTITLE__</p></div>
  <div class="seam" style="--pitch:11px"></div>
  <div class="controls">
    <input type="search" id="filter" placeholder="filter by file or text...">
    <button id="changed-only" class="btn-chrome" type="button" aria-pressed="false">Changed only</button>
    <button id="reset-all" class="btn-chrome" type="button">Revert all</button>
  </div>
</header>
<main id="list"></main>
</div>
<footer>
  <span class="count"><b id="n">0</b> &nbsp;field(s) changed</span>
  <button id="copy" type="button" disabled>Copy edits</button>
  <span id="toast"></span>
</footer>
<script>__SCRIPT__</script>
</body>
</html>
"""


def build_html(title, subtitle, sentinel, storage_key, cards):
    script = (SCRIPT
              .replace("__DATA__", json.dumps(cards, ensure_ascii=False))
              .replace("__SENTINEL__", sentinel)
              .replace("__STORAGE__", storage_key))
    return (PAGE
            .replace("__TITLE__", title)
            .replace("__SUBTITLE__", subtitle)
            .replace("__STYLE__", STYLE)
            .replace("__SCRIPT__", script))
