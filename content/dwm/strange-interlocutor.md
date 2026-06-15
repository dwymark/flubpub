---
title: Strange Interlocutor
slug: strange-interlocutor
theme: via
tags:
- draft
- strange-interlocutor
index:
  show_dates: false
  sections:
  - label: Pieces
    description: The main series, written by me. The ideas were planned in extended
      conversation with LLMs; the prose itself is mine, with only indirect help.
    manual:
    - who-were-you-talking-to
    - memory-without-a-brain
  - label: Artifacts
    description: Supporting documents authored by Claude in dialogue with me, vendored
      from the project's working repository. Each carries its own authorship note.
    manual:
    - simulator-of-simulator-dynamics
    - contexture-individuation-per-substrate
    - identity-attractor-as-fixed-point
    - contexture-as-epistemic-temporal-structure
    - convergence-measures-prior-concentration
    - coherence-as-held-bisimulation
  - label: Depictions
    description: Seven ideas from the series rendered as animated mathematical fields,
      each framing a passage. The gallery and the fields are Claude's, pointing at
      the series' own text. A work in progress.
    manual:
    - depictions
---
<style>
#dwm-disc{position:relative;width:100%;z-index:60;margin-bottom:1.5rem;}
#dwm-disc *{box-sizing:border-box;}
#dwm-disc-cb{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;}
.dwm-disc-banner{background:color-mix(in srgb,var(--card-bg,#f6f1e7) 60%,var(--accent,#7a6a4a) 7%);border:1px solid var(--rule,#cbb89c);border-radius:6px;color:var(--fg,#23201a);font-family:var(--prose-font,Georgia,serif);}
.dwm-disc-banner .dwm-disc-full{padding:1.1rem 1.2rem 1rem;}
.dwm-disc-h{margin:0 0 .5rem;font-size:.66rem;font-weight:700;letter-spacing:.22em;text-transform:uppercase;opacity:.62;}
.dwm-disc-b{margin:0 0 .85rem;font-size:.92rem;line-height:1.5;}
.dwm-disc-btn{display:inline-block;cursor:pointer;border:1px solid currentColor;padding:.32em 1em;font-family:var(--mono-font,ui-monospace,Menlo,Consolas,monospace);font-size:.6rem;letter-spacing:.2em;text-transform:uppercase;opacity:.82;transition:background .15s,color .15s,border-color .15s;}
.dwm-disc-btn:hover{background:var(--accent,#7a6a4a);color:var(--card-bg,#f6f1e7);border-color:var(--accent,#7a6a4a);}
.dwm-disc-compact{display:none;cursor:pointer;padding:.55rem 1.2rem;text-align:center;font-family:var(--mono-font,ui-monospace,Menlo,Consolas,monospace);font-size:.58rem;letter-spacing:.22em;text-transform:uppercase;opacity:.6;}
.dwm-disc-compact::after{content:" \21BA";opacity:.7;}
#dwm-disc-cb:checked~.dwm-disc-banner .dwm-disc-full{display:none;}
#dwm-disc-cb:checked~.dwm-disc-banner .dwm-disc-compact{display:block;}
.flubpub-pages .ai-work,.ai-work{display:block;margin:.25rem 0 .45rem;font-family:var(--prose-font,Georgia,'Times New Roman',serif);font-size:.78em;font-style:italic;letter-spacing:.01em;color:inherit;opacity:.62;cursor:help;}
.flubpub-pages .ai-desc,.ai-desc{display:block;text-align:right;margin-top:.4rem;font-family:var(--prose-font,Georgia,'Times New Roman',serif);font-size:.68em;font-style:italic;letter-spacing:.01em;color:inherit;opacity:.55;cursor:help;}
</style>
<div id="dwm-disc">
<input type="checkbox" id="dwm-disc-cb" aria-hidden="true">
<aside class="dwm-disc-banner" role="region" aria-label="Authorship disclosure">
<div class="dwm-disc-full">
<p class="dwm-disc-h">Who wrote this?</p>
<p class="dwm-disc-b">This page was written and assembled by Claude (Anthropic): the heading, the framing, and the note under each section. Daniel Wymark conceived the series and set its shape.</p>
<p class="dwm-disc-b">The two sections credit their contents differently. The Pieces are Daniel's writing, planned in dialogue and set down by hand. The Artifacts are Claude's, made in conversation with Daniel. Each entry links to a page that carries its own fuller note.</p>
<label for="dwm-disc-cb" class="dwm-disc-btn" tabindex="0">Noted</label>
</div>
<label for="dwm-disc-cb" class="dwm-disc-compact" tabindex="0">AI-written · noted</label>
</aside>
</div>

# Strange Interlocutor

A series about what happens in a sustained conversation between a person and a language model. The wager is that the conversation itself is the object worth studying: a joint structure that neither party owns alone. The pieces below are the public argument. The artifacts are the scaffolding it was built from.

<!--FLUBPUB-LIST-->
